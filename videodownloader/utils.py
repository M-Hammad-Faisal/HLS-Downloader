import subprocess
from pathlib import Path

import aiohttp


async def fetch_text(session: aiohttp.ClientSession, url: str, headers: dict):
    """Fetch text content from a URL using an existing aiohttp session.
    
    Args:
        session: aiohttp ClientSession for making the request
        url: URL to fetch content from
        headers: HTTP headers to include in the request
        
    Returns:
        Text content of the response
        
    Raises:
        aiohttp.ClientError: If the HTTP request fails
    """
    async with session.get(url, headers=headers) as r:
        r.raise_for_status()
        return await r.text()


async def fetch_bytes(session: aiohttp.ClientSession, url: str, headers: dict):
    """Fetch binary content from a URL using an existing aiohttp session.
    
    Args:
        session: aiohttp ClientSession for making the request
        url: URL to fetch content from
        headers: HTTP headers to include in the request
        
    Returns:
        Binary content of the response
        
    Raises:
        aiohttp.ClientError: If the HTTP request fails
    """
    async with session.get(url, headers=headers) as r:
        r.raise_for_status()
        return await r.read()


def concat_ts(paths, out_path: Path):
    """Concatenate multiple TS files into a single output file.
    
    Args:
        paths: List of file paths to concatenate
        out_path: Output file path for the concatenated result
        
    Raises:
        OSError: If file reading or writing fails
    """
    with open(out_path, "wb") as out:
        for p in paths:
            with open(p, "rb") as f:
                out.write(f.read())


def remux_to_mp4(ts_path: Path, mp4_path: Path, log_fn=None):
    """Remux a TS file to MP4 format using ffmpeg.
    
    Args:
        ts_path: Input TS file path
        mp4_path: Output MP4 file path
        log_fn: Optional logging function to call with command info
        
    Raises:
        subprocess.CalledProcessError: If ffmpeg command fails
        FileNotFoundError: If ffmpeg is not found in PATH
    """
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