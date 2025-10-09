import re
import asyncio
from pathlib import Path
from urllib.parse import urljoin, urlparse

import aiohttp

from .utils import fetch_bytes

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


class Variant:
    """Represents an HLS stream variant with bandwidth and resolution information."""
    
    def __init__(self, uri, bandwidth=None, resolution=None):
        self.uri = uri
        self.bandwidth = bandwidth
        self.resolution = resolution


class KeyInfo:
    """Represents encryption key information for HLS segments."""
    
    def __init__(self, method="NONE", uri=None, iv=None):
        self.method = method
        self.uri = uri
        self.iv = iv


class Segment:
    """Represents an HLS media segment with duration, encryption, and sequence information."""
    
    def __init__(self, uri, duration=None, key: KeyInfo = None, seq=None):
        self.uri = uri
        self.duration = duration
        self.key = key
        self.seq = seq


def normalize_uri(base_url: str, uri: str) -> str:
    """
    Make a playlist URI absolute.

    Handles:
    - Absolute URLs: return as-is
    - Scheme-less URLs: //host/path → scheme from base
    - Relative paths: use urljoin(base, path)
    - Paths that embed a hostname: /host.tld/… → scheme://host.tld/…
    """
    if not uri:
        return uri
    u = uri.strip()
    # Already absolute
    if u.startswith("http://") or u.startswith("https://"):
        return u
    # Scheme-less
    if u.startswith("//"):
        base = urlparse(base_url)
        return f"{base.scheme}:{u}"
    # Site-relative path
    if u.startswith("/"):
        # Prefer joining to base_url to preserve proxy-style paths (e.g., *.workers.dev)
        # If a path embeds a hostname like /example.com/..., proxies often rely on path rewriting.
        # Joining to base_url keeps requests going through the proxy.
        return urljoin(base_url, u)
    # Default relative resolution
    return urljoin(base_url, u)


def parse_resolution(s: str):
    """Parse a resolution string (e.g., '1920x1080') into a tuple of integers.
    
    Args:
        s: Resolution string in format 'WIDTHxHEIGHT'
        
    Returns:
        Tuple of (width, height) as integers, or None if parsing fails
    """
    m = re.match(r"^\s*(\d+)\s*x\s*(\d+)\s*$", s or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_master_playlist(text: str, base_url: str):
    """Parse an HLS master playlist to extract stream variants.
    
    Args:
        text: Master playlist content as string
        base_url: Base URL for resolving relative URIs
        
    Returns:
        List of Variant objects with bandwidth and resolution information
    """
    variants, attrs = [], {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs = {}
            for part in line.split(":", 1)[1].split(","):
                k, _, v = part.partition("=")
                attrs[k.strip().upper()] = v.strip()
        elif line and not line.startswith("#"):
            if attrs:
                bw = attrs.get("BANDWIDTH")
                res = attrs.get("RESOLUTION")
                bandwidth = int(bw) if bw and bw.isdigit() else None
                resolution = None
                if res and "x" in res:
                    try:
                        w, h = res.lower().split("x")
                        resolution = (int(w), int(h))
                    except:
                        pass
                variants.append(Variant(normalize_uri(base_url, line), bandwidth, resolution))
                attrs = {}
    return variants


def parse_media_playlist(text: str, base_url: str):
    """Parse an HLS media playlist to extract segments.
    
    Args:
        text: Media playlist content as string
        base_url: Base URL for resolving relative URIs
        
    Returns:
        List of Segment objects with duration, encryption, and sequence information
    """
    segments = []
    key = KeyInfo("NONE")
    seq = 0
    current_dur = None

    iv_re = re.compile(r"IV=0x([0-9A-Fa-f]+)")
    uri_re = re.compile(r'URI="([^"]+)"')
    method_re = re.compile(r"METHOD=([^,]+)")

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                seq = int(line.split(":", 1)[1])
            except:
                pass
        elif line.startswith("#EXTINF:"):
            try:
                current_dur = float(line.split(":", 1)[1].rstrip(","))
            except:
                current_dur = None
        elif line.startswith("#EXT-X-KEY:"):
            m_method = method_re.search(line)
            m_uri = uri_re.search(line)
            m_iv = iv_re.search(line)
            method = m_method.group(1) if m_method else "NONE"
            uri = normalize_uri(base_url, m_uri.group(1)) if m_uri else None
            iv = bytes.fromhex(m_iv.group(1)) if m_iv else None
            key = KeyInfo(method, uri, iv)
        elif line and not line.startswith("#"):
            seg_url = normalize_uri(base_url, line)
            lower = seg_url.lower()
            non_media_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico", ".css", ".js", ".html", ".txt")
            is_media = (lower.endswith(".ts") or lower.endswith(".m4s") or lower.endswith(".mp4") or ".ts?" in lower or ".m4s?" in lower or ".mp4?" in lower)
            if not is_media and any(lower.endswith(ext) for ext in non_media_exts):
                continue
            segments.append(Segment(seg_url, duration=current_dur, key=key, seq=seq))
            seq += 1
            current_dur = None
    return segments


def select_variant(variants, want_res=None, want_bw=None):
    """Select the best variant from available options based on resolution or bandwidth preferences.
    
    Args:
        variants: List of Variant objects to choose from
        want_res: Desired resolution as (width, height) tuple
        want_bw: Desired maximum bandwidth in bits per second
        
    Returns:
        Best matching Variant object, or None if no variants available
    """
    if not variants:
        return None
    if want_res:
        w, h = want_res
        exact = [v for v in variants if v.resolution == (w, h)]
        if exact:
            return exact[0]
        ordered = sorted(variants, key=lambda v: (v.resolution[1] if v.resolution else 0, v.bandwidth or 0))
        best = None
        for v in ordered:
            if v.resolution and v.resolution[1] <= h:
                best = v
        return best or ordered[-1]
    if want_bw:
        cands = [v for v in variants if (v.bandwidth or 0) <= want_bw]
        if cands:
            return sorted(cands, key=lambda v: v.bandwidth or 0)[-1]
        return sorted(variants, key=lambda v: v.bandwidth or 0)[-1]
    return sorted(variants, key=lambda v: v.bandwidth or 0)[-1]


async def download_segment(session, seg: Segment, headers, idx: int, temp_dir: Path, cancel_flag):
    """Download a single HLS segment with optional AES-128 decryption.
    
    Args:
        session: aiohttp ClientSession for making requests
        seg: Segment object containing URI and encryption info
        headers: HTTP headers to include in requests
        idx: Segment index for filename generation
        temp_dir: Directory to save downloaded segments
        cancel_flag: asyncio.Event to signal cancellation
        
    Returns:
        Path to downloaded segment file, or None if cancelled/failed
    """
    if cancel_flag.is_set():
        return None
    path = temp_dir / f"seg_{idx:06d}.ts"
    if path.exists() and path.stat().st_size > 0:
        return path
    data = await fetch_bytes(session, seg.uri, headers)

    if seg.key and seg.key.method and seg.key.method.upper() == "AES-128":
        if AES is None:
            raise RuntimeError("Install pycryptodome for AES-128: pip install pycryptodome")
        if not seg.key.uri:
            raise RuntimeError("Key URI missing for AES-128 segment.")
        key_bytes = await fetch_bytes(session, seg.key.uri, headers)
        iv = seg.key.iv or (seg.seq.to_bytes(16, "big") if seg.seq is not None else (0).to_bytes(16, "big"))
        data = AES.new(key_bytes, AES.MODE_CBC, iv=iv).decrypt(data)

    with open(path, "wb") as f:
        f.write(data)
    return path


async def download_all_segments(session, segments, headers, concurrency, temp_dir: Path, log_fn, progress_fn, cancel_flag):
    """Download all HLS segments concurrently with progress tracking.
    
    Args:
        session: aiohttp ClientSession for making requests
        segments: List of Segment objects to download
        headers: HTTP headers to include in requests
        concurrency: Maximum number of concurrent downloads
        temp_dir: Directory to save downloaded segments
        log_fn: Function to call for logging messages
        progress_fn: Function to call with (completed, total) progress updates
        cancel_flag: asyncio.Event to signal cancellation
        
    Returns:
        List of successfully downloaded segment file paths
    """
    sem = asyncio.Semaphore(concurrency)
    results = [None] * len(segments)

    async def worker(i, seg):
        if cancel_flag.is_set():
            return
        async with sem:
            results[i] = await download_segment(session, seg, headers, i, temp_dir, cancel_flag)
            if cancel_flag.is_set():
                return
            done = sum(1 for r in results if r is not None)
            progress_fn(done, len(segments))

    tasks = [asyncio.create_task(worker(i, s)) for i, s in enumerate(segments)]
    for t in asyncio.as_completed(tasks):
        if cancel_flag.is_set():
            break
        try:
            await t
        except Exception as e:
            log_fn(f"Segment error: {e}")

    return [p for p in results if p is not None]