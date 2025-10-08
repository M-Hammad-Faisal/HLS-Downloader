from pathlib import Path

import aiohttp


async def download_http(url: str, out_path: Path, headers: dict):
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
    conn = aiohttp.TCPConnector(limit=8)
    async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
        async with session.get(url, headers=headers) as r:
            r.raise_for_status()
            total = r.headers.get("Content-Length")
            total = int(total) if total and total.isdigit() else None
            done = 0
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as f:
                async for chunk in r.content.iter_chunked(64 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = int(done / total * 100)
                        print(f"Downloading — {pct}%\r", end="")
            print("\nSaved:", out_path)