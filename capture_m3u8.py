#!/usr/bin/env python3
"""
CLI to capture .m3u8 from a page and optionally download it.

Requires:
- pip install playwright
- playwright install chromium

Authorized use only. Do not use to bypass DRM or scrape piracy sites.
"""

import sys
import argparse
import subprocess
from pathlib import Path

from videodownloader.capture import capture_media

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chromium/124.0.0.0 Safari/537.36"
)


def build_argparser():
    """
    Build and configure the argument parser for the capture CLI.
    
    Returns:
        argparse.ArgumentParser: Configured argument parser with all CLI options.
    """
    p = argparse.ArgumentParser(description="Capture .m3u8 URLs from a web page")
    p.add_argument("--page", required=True, help="Page URL to open")
    p.add_argument("--ua", help="User-Agent header for requests")
    p.add_argument("--ref", help="Referer header for requests")
    p.add_argument("--cookies", help="Cookie header string for requests")
    p.add_argument("--headless", action="store_true", help="Run browser headless (default)")
    p.add_argument("--no-headless", action="store_true", help="Run with visible browser")
    p.add_argument("--timeout", type=int, default=20, help="Wait time for network idle in seconds")
    p.add_argument("--download", action="store_true", help="Automatically download the first captured .m3u8")
    p.add_argument("--print-cookie", action="store_true", help="Print synthesized Cookie header from browser session")
    p.add_argument("--include-body", action="store_true", help="Fetch m3u8 text bodies for responses (for inspection)")
    p.add_argument("--out", default=str(Path.cwd() / "downloads" / "output.mp4"), help="Output path for download")
    return p


def main():
    """
    Main entry point for the capture CLI application.
    
    Parses command line arguments, captures media URLs from a web page,
    and optionally downloads the first captured M3U8 stream.
    """
    args = build_argparser().parse_args()
    headers = {}
    headers["User-Agent"] = args.ua or DEFAULT_UA
    if args.ref:
        headers["Referer"] = args.ref
    if args.cookies:
        headers["Cookie"] = args.cookies

    headless = True
    if args.no_headless:
        headless = False
    elif args.headless:
        headless = True

    items, cookie_header = capture_media(
        args.page,
        headers=headers,
        headless=headless,
        timeout_seconds=args.timeout,
        verbose=True,
        include_m3u8_body=args.include_body,
    )

    if args.print_cookie:
        print("\nCookie header:")
        print(cookie_header or "<none>")

    if not items:
        print("No .m3u8 URLs captured.")
        sys.exit(2)

    print("Captured media:")
    for i, it in enumerate(items, 1):
        label = it.get("content_type") or ""
        print(f"  {i}. [{it['kind']}] {it['url']} {label}")
        if args.include_body and it.get("body"):
            print("       --- m3u8 body snippet ---")
            snippet = it["body"][:200].replace("\n", " ")
            print("       ", snippet, "…")

    if args.download:
        first = None
        for it in items:
            u = it["url"].lower()
            ct = (it.get("content_type") or "").lower()
            if ".m3u8" in u or "mpegurl" in ct:
                first = it["url"]
                break
        if not first:
            print("No .m3u8 found among captured items to download.")
            sys.exit(3)
        print("\nDownloading first captured .m3u8:", first)
        cmd = [
            sys.executable,
            "cli_downloader.py",
            "--url",
            first,
            "--out",
            args.out,
        ]
        cmd += ["--ua", args.ua or DEFAULT_UA]
        if args.ref:
            cmd += ["--ref", args.ref]
        else:
            cmd += ["--ref", args.page]
        if args.cookies:
            cmd += ["--cookies", args.cookies]
        elif cookie_header:
            cmd += ["--cookies", cookie_header]

        print("Running:", " ".join(cmd))
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            print("Downloader error:", e)
            sys.exit(1)


if __name__ == "__main__":
    main()