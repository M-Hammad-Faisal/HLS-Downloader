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
    parse_resolution,
    download_all_segments,
)
from .capture import capture_media, DEFAULT_UA as CAPTURE_DEFAULT_UA

import aiohttp

DEFAULT_UA = CAPTURE_DEFAULT_UA


def derive_output_from_url(url: str, downloads_dir: Path) -> Path:
    """Derive a nested output path mirroring the URL: domain/path/file.mp4.

    Examples:
      https://111movies.com/tv/48866/1/10 -> downloads/111movies.com/tv/48866/1/10.mp4
    """
    try:
        u = urlparse(url)
        netloc = u.netloc or "unknown-host"

        def sanitize(s: str) -> str:
            s2 = "".join(c for c in s if c.isalnum() or c in ("-", "_", "."))
            return (s2 or "_")[:64]

        base = downloads_dir / sanitize(netloc)
        # split and sanitize path segments
        segs = [sanitize(seg) for seg in (u.path or "").split("/") if seg]
        if not segs:
            segs = ["video"]
        # last segment becomes filename stem; strip playlist extensions if present
        stem = segs[-1]
        lower = stem.lower()
        if lower.endswith(".m3u8"):
            stem = stem[:-5]
        elif lower.endswith(".mp4"):
            stem = stem[:-4]
        elif lower.endswith(".ts"):
            stem = stem[:-3]
        # directory is all but last
        nested_dir = base.joinpath(*segs[:-1]) if len(segs) > 1 else base
        return nested_dir / f"{stem}.mp4"
    except Exception:
        return downloads_dir / sanitize("output") / "video.mp4"


async def download_hls(url: str, out_path: Path, res_text: str, bw: int, ua: str, ref: str, cookies: str, conc: int, remux: bool):
    """
    Download an HLS stream to a local file.
    
    Args:
        url: The M3U8 playlist URL to download.
        out_path: Output file path for the downloaded video.
        res_text: Preferred resolution string (e.g., "1920x1080").
        bw: Preferred bandwidth in bits per second.
        ua: User-Agent header value.
        ref: Referer header value.
        cookies: Cookie header string.
        conc: Number of concurrent segment downloads.
        remux: Whether to remux the final output to MP4.
    """
    headers = {}
    if ua:
        headers["User-Agent"] = ua
    if ref:
        headers["Referer"] = ref
    if cookies:
        headers["Cookie"] = cookies

    out_path.parent.mkdir(parents=True, exist_ok=True)

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
    conn = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
        print("[1/5] Fetching playlist…")
        text = await fetch_text(session, url, headers)

        base = url
        if "#EXT-X-STREAM-INF" in text:
            print("[2/5] Master playlist detected. Selecting variant…")
            variants = parse_master_playlist(text, base)
            if not variants:
                raise RuntimeError("No variants found in master playlist.")
            want_res = parse_resolution(res_text) if res_text else None
            chosen = select_variant(variants, want_res=want_res, want_bw=bw)
            print(f"Chosen: {chosen.resolution or 'unknown'} @ {chosen.bandwidth or 'n/a'} → {chosen.uri}")
            text = await fetch_text(session, chosen.uri, headers)
            base = chosen.uri
        else:
            print("[2/5] Media playlist detected.")

        if "EXT-X-KEY" in text and "METHOD=SAMPLE-AES" in text:
            raise RuntimeError("DRM detected (SAMPLE-AES). Not supported.")

        print("[3/5] Parsing segments…")
        segments = parse_media_playlist(text, base)
        if not segments:
            raise RuntimeError("No segments found in playlist.")

        print(f"[4/5] Downloading {len(segments)} segments (concurrency={conc})…")
        last_pct = -1

        def progress_fn(done, total_):
            nonlocal last_pct
            pct = int(done / total_ * 100)
            if pct != last_pct:
                print(f"Downloading — {pct}%\r", end="")
                last_pct = pct

        cancel_flag = asyncio.Event()
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            paths = await download_all_segments(session, segments, headers, max(1, int(conc or 8)), temp_dir, print, progress_fn, cancel_flag)
            if cancel_flag.is_set():
                raise RuntimeError("Cancelled")

            print("\n[5/5] Concatenating segments…")
            merged_ts = temp_dir / "merged.ts"
            concat_ts(paths, merged_ts)

            if remux:
                final_mp4 = out_path if out_path.suffix.lower() == ".mp4" else out_path.with_suffix(".mp4")
                remux_to_mp4(merged_ts, final_mp4)
                print("Saved:", final_mp4)
            else:
                final_ts = out_path if out_path.suffix.lower() == ".ts" else out_path.with_suffix(".ts")
                final_ts.write_bytes(merged_ts.read_bytes())
                print("Saved:", final_ts)


def get_page_url():
    """Prompt user for page URL input."""
    while True:
        page_url = input("Enter the web page URL that plays the video: ").strip()
        if page_url:
            return page_url
        print("Please enter a valid URL.")


def get_user_agent():
    """Prompt user for user-agent with default option."""
    print(f"\nUser-Agent (press Enter for default):")
    print(f"Default: {DEFAULT_UA}")
    ua = input("Enter User-Agent: ").strip()
    if not ua:
        ua = DEFAULT_UA
        print(f"Using default User-Agent: {ua}")
    return ua


def get_timeout():
    """Prompt user for timeout with default option."""
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
    """Interactive resolution selection from captured media items."""
    # Filter for media-related items (M3U8, MP4, TS files)
    media_items = []
    for item in captured_items:
        url = item.get("url", "") or ""
        content_type = item.get("content_type", "") or ""
        url_lower = url.lower()
        content_type_lower = content_type.lower()
        
        # Include items that are likely media files
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
        # Show a shortened URL for better readability
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
    """
    Build and configure the argument parser for the CLI downloader.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser with all CLI options.
    """
    p = argparse.ArgumentParser(description="Authorized Video Downloader (HTTP/HLS)")
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
    p.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode (default)")
    p.add_argument("--no-headless", action="store_true", help="Run browser with GUI (for debugging)")
    return p


def decide_mode(url: str, mode_arg: str):
    """
    Determine the download mode based on URL and user preference.
    
    Args:
        url: The source URL to analyze.
        mode_arg: User-specified mode ("auto", "http", or "hls").
        
    Returns:
        str: The determined download mode ("http" or "hls").
    """
    if mode_arg != "auto":
        return mode_arg
    u = url.lower()
    if ".m3u8" in u:
        return "hls"
    return "http"


def main():
    """
    Main entry point for the CLI downloader application.
    
    Supports both interactive mode (like GUI) and direct URL mode (original CLI).
    """
    args = build_argparser().parse_args()
    
    # Determine if we should use interactive mode
    use_interactive = args.interactive or not args.url
    
    if use_interactive:
        # Interactive mode - matches GUI workflow
        print("=== Interactive Video Downloader ===")
        
        # Step 1: Get page URL
        page_url = get_page_url()
        
        # Step 2: Get user agent
        ua = get_user_agent()
        
        # Step 3: Get timeout
        timeout = get_timeout()
        
        # Step 4: Run Playwright capture
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
            
            # Step 5: Interactive resolution selection
            selected_url = select_resolution_interactive(captured_items)
            if not selected_url:
                print("No media item selected. Exiting.")
                sys.exit(1)
            
            # Update headers with captured cookie if available
            if cookie_header:
                headers["Cookie"] = cookie_header
                print(f"Using captured cookies for download.")
            
            # Step 6: Download with progress
            print(f"\nPage URL: {page_url}")
            print(f"Selected Media URL: {selected_url}")
            url = selected_url
            
            # Use page URL for directory structure, not the M3U8 URL
            use_interactive = True
            
        except Exception as e:
            print(f"Error during capture: {e}")
            sys.exit(1)
    else:
        # Direct URL mode - original CLI behavior
        url = args.url
        use_interactive = False
        headers = {}
        if args.ua:
            headers["User-Agent"] = args.ua
        if args.ref:
            headers["Referer"] = args.ref
        if args.cookies:
            headers["Cookie"] = args.cookies
    
    # Common download logic for both modes
    default_out = Path.cwd() / "downloads" / "output.mp4"
    out_path = Path(args.out)
    if out_path == default_out:
        if use_interactive:
            # Use page URL for directory structure, but extract filename from media URL
            page_path = derive_output_from_url(page_url, default_out.parent)
            media_path = derive_output_from_url(url, default_out.parent)
            # Use page URL directory structure with media URL filename
            out_path = page_path.parent / media_path.name
        else:
            out_path = derive_output_from_url(url, default_out.parent)
    
    mode = decide_mode(url, args.mode)
    
    # Set up headers for download
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
            asyncio.run(download_hls(url, out_path, args.res, args.bw or None, args.ua, args.ref, args.cookies, args.conc, remux=(not args.no_remux)))
        print("Download completed successfully!")
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()