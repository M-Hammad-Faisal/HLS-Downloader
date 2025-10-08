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

import aiohttp

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chromium/124.0.0.0 Safari/537.36"
)


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


def build_argparser():
    p = argparse.ArgumentParser(description="Authorized Video Downloader (HTTP/HLS)")
    p.add_argument("--url", required=True, help="Source URL (direct media or .m3u8)")
    p.add_argument("--out", default=str(Path.cwd() / "downloads" / "output.mp4"), help="Output file path")
    p.add_argument("--mode", choices=["auto", "http", "hls"], default="auto", help="Download mode")
    p.add_argument("--ua", default=DEFAULT_UA, help="User-Agent header")
    p.add_argument("--ref", help="Referer header")
    p.add_argument("--cookies", help="Cookie header string")
    p.add_argument("--res", help="Preferred resolution for HLS, e.g., 1920x1080")
    p.add_argument("--bw", type=int, help="Preferred bandwidth for HLS in bps")
    p.add_argument("--conc", type=int, default=4, help="HLS segment concurrency")
    p.add_argument("--no-remux", action="store_true", help="Do not remux HLS to MP4 (keep .ts)")
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
    url = args.url
    default_out = Path.cwd() / "downloads" / "output.mp4"
    out_path = Path(args.out)
    if out_path == default_out:
        out_path = derive_output_from_url(url, default_out.parent)
    mode = decide_mode(url, args.mode)
    headers = {}
    if args.ua:
        headers["User-Agent"] = args.ua
    if args.ref:
        headers["Referer"] = args.ref
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
    headers.setdefault("Accept-Encoding", "gzip, deflate, br")
    if args.cookies:
        headers["Cookie"] = args.cookies

    print(f"Mode: {mode}")
    try:
        if mode == "http":
            asyncio.run(download_http(url, out_path, headers))
        else:
            asyncio.run(download_hls(url, out_path, args.res, args.bw or None, args.ua, args.ref, args.cookies, args.conc, remux=(not args.no_remux)))
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()