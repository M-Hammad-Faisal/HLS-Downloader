#!/usr/bin/env python3
import sys
from pathlib import Path
import argparse
import asyncio
import tempfile
from urllib.parse import urlparse

from .http_dl import download_http
from .utils import fetch_text, concat_ts, remux_to_mp4
from .hls import (
    parse_master_playlist,
    parse_media_playlist,
    select_variant,
    download_all_segments,
)
from .capture import capture_media, DEFAULT_UA as CAPTURE_DEFAULT_UA

import aiohttp

DEFAULT_UA = CAPTURE_DEFAULT_UA


def derive_output_from_url(url: str, downloads_dir: Path) -> Path:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or "unknown"
        path_parts = [p for p in parsed.path.split("/") if p and p != "index.html"]
        
        if path_parts:
            filename = path_parts[-1]
            if "." in filename:
                name, ext = filename.rsplit(".", 1)
                if ext.lower() in ["m3u8", "ts", "mp4", "mkv", "avi", "mov"]:
                    filename = f"{name}.mp4"
                else:
                    filename = f"{filename}.mp4"
            else:
                filename = f"{filename}.mp4"
        else:
            filename = "video.mp4"
        
        safe_domain = "".join(c if c.isalnum() or c in ".-_" else "_" for c in domain)
        safe_filename = "".join(c if c.isalnum() or c in ".-_" else "_" for c in filename)
        
        output_dir = downloads_dir / safe_domain
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return output_dir / safe_filename
    except Exception:
        return downloads_dir / "video.mp4"


async def download_hls(url, out_path, res_text, bw, headers, conc, remux):
    async with aiohttp.ClientSession() as session:
        print("Fetching master playlist...")
        master_text = await fetch_text(session, url, headers)
        
        variants = parse_master_playlist(master_text, url)
        if not variants:
            print("No variants found, treating as media playlist...")
            segments = parse_media_playlist(master_text, url)
        else:
            print(f"Found {len(variants)} variants")
            chosen = select_variant(variants, res_text, bw)
            print(f"Selected variant: {chosen.resolution or 'unknown'} @ {chosen.bandwidth or 'unknown'} bps")
            
            media_text = await fetch_text(session, chosen.uri, headers)
            segments = parse_media_playlist(media_text, chosen.uri)
        
        print(f"Found {len(segments)} segments")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            await download_all_segments(session, segments, temp_path, headers, conc)
            
            concat_path = temp_path / "concat.ts"
            concat_ts(temp_path, concat_path)
            
            if remux:
                print("Remuxing to MP4...")
                remux_to_mp4(concat_path, out_path)
            else:
                print("Copying TS file...")
                import shutil
                shutil.copy2(concat_path, out_path)


def get_page_url():
    while True:
        page_url = input("\nEnter the page URL to capture media from: ").strip()
        if page_url:
            if not page_url.startswith(("http://", "https://")):
                page_url = "https://" + page_url
            return page_url
        print("Please enter a valid URL.")


def get_user_agent():
    print(f"\nUser-Agent (press Enter for default):")
    print(f"Default: {DEFAULT_UA}")
    ua = input("Enter User-Agent: ").strip()
    if not ua:
        ua = DEFAULT_UA
        print(f"Using default User-Agent: {ua}")
    return ua


def get_timeout():
    while True:
        timeout_input = input("\nEnter timeout in seconds (press Enter for default 30): ").strip()
        if not timeout_input:
            timeout = 30
            print(f"Using default timeout: {timeout} seconds")
            return timeout
        try:
            timeout = int(timeout_input)
            if timeout > 0:
                return timeout
            else:
                print("Timeout must be a positive number.")
        except ValueError:
            print("Please enter a valid number.")


def select_resolution_interactive(captured_items):
    media_items = []
    for item in captured_items:
        url = item.get("url", "") or ""
        content_type = item.get("content_type", "") or ""
        url_lower = url.lower()
        content_type_lower = content_type.lower()
        
        if (url_lower.endswith('.m3u8') or 
            url_lower.endswith('.mp4') or 
            url_lower.endswith('.ts') or
            '.m3u8' in url_lower or
            'video' in content_type_lower or
            'application/vnd.apple.mpegurl' in content_type_lower or
            'application/x-mpegurl' in content_type_lower):
            media_items.append(item)
    
    if not media_items:
        print("No media items found in captured data.")
        print("Captured items:")
        for i, item in enumerate(captured_items, 1):
            url = item.get("url", "")
            content_type = item.get("content_type", "")
            kind = item.get("kind", "")
            print(f"  {i}. [{kind}] {url} {content_type}")
        return None
    
    print("\nCaptured media items:")
    for i, item in enumerate(media_items, 1):
        url = item.get("url", "")
        content_type = item.get("content_type", "")
        kind = item.get("kind", "")
        display_url = url if len(url) <= 80 else url[:77] + "..."
        print(f"  {i}. [{kind}] {display_url}")
        if content_type:
            print(f"      Content-Type: {content_type}")
    
    while True:
        try:
            choice = input(f"\nSelect media item to download (1-{len(media_items)}): ").strip()
            if not choice:
                continue
            index = int(choice) - 1
            if 0 <= index < len(media_items):
                selected_item = media_items[index]
                print(f"Selected: {selected_item['url']}")
                return selected_item['url']
            else:
                print(f"Please enter a number between 1 and {len(media_items)}")
        except ValueError:
            print("Please enter a valid number.")


def build_argparser():
    p = argparse.ArgumentParser(description="HLS Downloader - Download HLS streams and media files")
    p.add_argument("--url", help="Source URL (direct media or .m3u8) - if not provided, interactive mode will be used")
    p.add_argument("--interactive", "-i", action="store_true", help="Force interactive mode (capture from page)")
    p.add_argument("--out", default=str(Path.cwd() / "downloads" / "output.mp4"), help="Output file path")
    p.add_argument("--mode", choices=["auto", "http", "hls"], default="auto", help="Download mode")
    p.add_argument("--ua", default=DEFAULT_UA, help="User-Agent header")
    p.add_argument("--ref", help="Referer header")
    p.add_argument("--cookies", help="Cookie header string")
    p.add_argument("--res", help="Preferred resolution for HLS, e.g., 1920x1080")
    p.add_argument("--bw", type=int, help="Preferred bandwidth for HLS in bps")
    p.add_argument("--conc", type=int, default=4, help="HLS segment concurrency")
    p.add_argument("--no-remux", action="store_true", help="Do not remux HLS to MP4 (keep .ts)")
    p.add_argument("--no-headless", action="store_true", help="Run browser with GUI (for debugging)")
    return p


def decide_mode(url: str, mode_arg: str):
    if mode_arg != "auto":
        return mode_arg
    u = url.lower()
    if ".m3u8" in u:
        return "hls"
    return "http"


def main():
    args = build_argparser().parse_args()
    
    use_interactive = args.interactive or not args.url
    
    if use_interactive:
        print("=== Interactive HLS Downloader ===")
        
        page_url = get_page_url()
        ua = get_user_agent()
        timeout = get_timeout()
        
        print(f"\nCapturing media from: {page_url}")
        print("Running Playwright to capture media URLs...")
        
        headers = {
            "User-Agent": ua,
            "Referer": page_url
        }
        
        if args.cookies:
            headers["Cookie"] = args.cookies
        
        headless = not args.no_headless
        
        try:
            captured_items, cookie_header = capture_media(
                page_url,
                headers=headers,
                headless=headless,
                timeout_seconds=timeout,
                verbose=True,
                include_m3u8_body=True
            )
            
            if not captured_items:
                print("No media items captured. Please check the page URL and try again.")
                sys.exit(1)
            
            print(f"Captured {len(captured_items)} items.")
            
            selected_url = select_resolution_interactive(captured_items)
            if not selected_url:
                print("No media item selected. Exiting.")
                sys.exit(1)
            
            if cookie_header:
                headers["Cookie"] = cookie_header
                print(f"Using captured cookies for download.")
            
            print(f"\nPage URL: {page_url}")
            print(f"Selected Media URL: {selected_url}")
            url = selected_url
            
            use_interactive = True
            
        except Exception as e:
            print(f"Error during capture: {e}")
            sys.exit(1)
    else:
        url = args.url
        use_interactive = False
        headers = {}
        if args.ua:
            headers["User-Agent"] = args.ua
        if args.ref:
            headers["Referer"] = args.ref
        if args.cookies:
            headers["Cookie"] = args.cookies
    
    default_out = Path.cwd() / "downloads" / "output.mp4"
    out_path = Path(args.out)
    if out_path == default_out:
        if use_interactive:
            out_path = derive_output_from_url(page_url, default_out.parent)
        else:
            out_path = derive_output_from_url(url, default_out.parent)
    
    mode = decide_mode(url, args.mode)
    
    if args.ref and not use_interactive:
        try:
            ro = urlparse(args.ref)
            origin = f"{ro.scheme}://{ro.netloc}" if ro.scheme and ro.netloc else None
        except Exception:
            origin = None
    else:
        try:
            uo = urlparse(url)
            origin = f"{uo.scheme}://{uo.netloc}" if uo.scheme and uo.netloc else None
        except Exception:
            origin = None
    
    if origin:
        headers["Origin"] = origin
    headers.setdefault("Accept", "*/*")
    headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    headers.setdefault("Accept-Encoding", "gzip, deflate")

    print(f"\nStarting download...")
    print(f"URL: {url}")
    print(f"Output: {out_path}")
    print(f"Mode: {mode}")
    
    try:
        if mode == "http":
            asyncio.run(download_http(url, out_path, headers))
        else:
            asyncio.run(download_hls(url, out_path, args.res, args.bw or None, headers, args.conc, remux=(not args.no_remux)))
        print("Download completed successfully!")
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()