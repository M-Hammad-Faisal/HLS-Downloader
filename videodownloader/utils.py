import subprocess
from pathlib import Path

import aiohttp


async def fetch_text(session: aiohttp.ClientSession, url: str, headers: dict):
    async with session.get(url, headers=headers) as r:
        r.raise_for_status()
        return await r.text()


async def fetch_bytes(session: aiohttp.ClientSession, url: str, headers: dict):
    async with session.get(url, headers=headers) as r:
        r.raise_for_status()
        return await r.read()


def concat_ts(paths, out_path: Path):
    with open(out_path, "wb") as out:
        for p in paths:
            with open(p, "rb") as f:
                out.write(f.read())


def remux_to_mp4(ts_path: Path, mp4_path: Path, log_fn=None):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(ts_path),
        "-c",
        "copy",
        str(mp4_path),
    ]
    if log_fn:
        log_fn("Remux: " + " ".join(cmd))
    subprocess.check_call(cmd)