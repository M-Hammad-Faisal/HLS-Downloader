"""
Capture media URLs by intercepting network traffic from a web page.
Requires: playwright (pip install playwright; then playwright install chromium)

Only for authorized, NON-DRM sources.
"""

from typing import List, Optional, Dict, Tuple
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chromium/124.0.0.0 Safari/537.36"
)


def capture_m3u8(
    page_url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    headless: bool = True,
    timeout_seconds: int = 20,
    verbose: bool = True,
) -> List[str]:
    """Legacy helper: returns a list of request URLs that contain .m3u8."""
    found: List[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(extra_http_headers=headers or {})
        page = context.new_page()

        def on_request(req):
            url = req.url.lower()
            if ".m3u8" in url:
                if verbose:
                    print("Found .m3u8:", req.url)
                found.append(req.url)

        page.on("request", on_request)

        page.goto(page_url, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000)
        except PlaywrightTimeoutError:
            pass

        context.close()
        browser.close()
    # Deduplicate preserving order
    seen = set()
    uniq = []
    for u in found:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def capture_media(
    page_url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    headless: bool = True,
    timeout_seconds: int = 20,
    verbose: bool = True,
    include_m3u8_body: bool = False,
) -> Tuple[List[dict], str]:
    """
    Capture media-related requests and responses.

    Returns (items, cookie_header) where items are dicts like:
      {"url": str, "kind": "request"|"response", "content_type": str|None, "body": str|None}

    cookie_header is a synthesized "Cookie" header from the browser context.
    """
    found: List[dict] = []
    # Track media activity per page to decide closing pop-ups
    page_media_counts: Dict[object, int] = {}
    # Prepare effective headers
    eff_headers = dict(headers or {})
    eff_headers.setdefault("User-Agent", DEFAULT_UA)
    eff_headers.setdefault("Accept", "*/*")
    eff_headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    # Derive Referer/Origin from page_url if not provided
    eff_headers.setdefault("Referer", page_url)
    try:
        uo = urlparse(eff_headers.get("Referer", page_url))
        origin = f"{uo.scheme}://{uo.netloc}" if uo.scheme and uo.netloc else None
    except Exception:
        origin = None
    if origin:
        eff_headers.setdefault("Origin", origin)

    with sync_playwright() as pw:
        # Launch Chromium with minimal automation fingerprinting
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=NetworkService",
            ],
        )
        # Create a context that looks like a normal user session
        context = browser.new_context(
            user_agent=eff_headers.get("User-Agent", DEFAULT_UA),
            extra_http_headers={k: v for k, v in eff_headers.items() if k.lower() != "user-agent"},
            ignore_https_errors=True,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="UTC",
            color_scheme="light",
        )
        # API request context that shares cookies/storage with the browser context
        try:
            api_ctx = pw.request.new_context(storage_state=context.storage_state())
        except Exception:
            api_ctx = None
        try:
            context.add_init_script(
                """
                // Reduce automation signals
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = window.chrome || { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                """
            )
        except Exception:
            pass
        page = context.new_page()

        def looks_like_media(url: str) -> bool:
            u = url.lower()
            return (
                ".m3u8" in u
                or u.endswith(".mp4")
                or u.endswith(".ts")
                or ".mp4?" in u
                or ".ts?" in u
            )

        def on_request(req, page_ref=None):
            url = req.url
            if looks_like_media(url):
                if verbose:
                    print("Request:", url)
                # Try to capture request headers and resource type
                try:
                    try:
                        req_headers = req.headers
                    except Exception:
                        req_headers = {}
                    if not isinstance(req_headers, dict):
                        try:
                            req_headers = dict(req_headers)
                        except Exception:
                            req_headers = {}
                except Exception:
                    req_headers = {}
                rtype = None
                try:
                    rtype = getattr(req, "resource_type", None)
                except Exception:
                    rtype = None
                frame_url = None
                try:
                    frame = getattr(req, "frame", None)
                    if frame:
                        frame_url = getattr(frame, "url", None)
                except Exception:
                    frame_url = None
                found.append({
                    "url": url,
                    "kind": "request",
                    "content_type": None,
                    "body": None,
                    "headers": req_headers,
                    "resource_type": rtype,
                    "page_url": getattr(page_ref, "url", None) if page_ref else page_url,
                    "frame_url": frame_url,
                })
                try:
                    if page_ref is not None:
                        page_media_counts[page_ref] = page_media_counts.get(page_ref, 0) + 1
                except Exception:
                    pass

        def on_response(resp, page_ref=None):
            url = resp.url
            ct = (resp.headers.get("content-type") or "").lower()
            hit = (
                looks_like_media(url)
                or "application/vnd.apple.mpegurl" in ct
                or "application/x-mpegurl" in ct
                or "video/mp4" in ct
                or "video/mp2t" in ct
            )
            if hit:
                body = None
                if include_m3u8_body and ("mpegurl" in ct or url.lower().endswith(".m3u8")):
                    try:
                        body = resp.text()
                    except Exception:
                        body = None
                    # Fallback: fetch m3u8 text via API context using the same cookies
                    if body is None and api_ctx is not None:
                        try:
                            hdrs = {
                                "User-Agent": eff_headers.get("User-Agent", DEFAULT_UA),
                                "Accept": eff_headers.get("Accept", "*/*"),
                                "Accept-Language": eff_headers.get("Accept-Language", "en-US,en;q=0.9"),
                            }
                            ref_val = eff_headers.get("Referer") or page_url
                            if ref_val:
                                hdrs["Referer"] = ref_val
                                try:
                                    ro = urlparse(ref_val)
                                    origin = f"{ro.scheme}://{ro.netloc}" if ro.scheme and ro.netloc else None
                                except Exception:
                                    origin = None
                                if origin:
                                    hdrs["Origin"] = origin
                            r = api_ctx.get(url, headers=hdrs, timeout=15000)
                            if getattr(r, "ok", False):
                                try:
                                    body = r.text()
                                except Exception:
                                    body = None
                        except Exception:
                            pass
                # Capture response headers if available
                resp_headers = {}
                try:
                    resp_headers = dict(resp.headers)
                except Exception:
                    try:
                        resp_headers = resp.headers
                    except Exception:
                        resp_headers = {}
                if verbose:
                    print("Response:", url, ct or "")
                found.append({
                    "url": url,
                    "kind": "response",
                    "content_type": ct or None,
                    "body": body,
                    "headers": resp_headers,
                    "page_url": getattr(page_ref, "url", None) if page_ref else page_url,
                })
                try:
                    if page_ref is not None:
                        page_media_counts[page_ref] = page_media_counts.get(page_ref, 0) + 1
                except Exception:
                    pass

        def attach_listeners(p):
            # Initialize media counter
            try:
                page_media_counts.setdefault(p, 0)
            except Exception:
                pass
            p.on("request", lambda req: on_request(req, page_ref=p))
            p.on("response", lambda resp: on_response(resp, page_ref=p))

        attach_listeners(page)

        # Also listen at the browser context level to capture requests from
        # service workers or frames not directly tied to the current Page object.
        try:
            context.on("request", lambda req: on_request(req))
        except Exception:
            pass
        try:
            context.on("response", lambda resp: on_response(resp))
        except Exception:
            pass

        def on_new_page(p):
            # Attach listeners to observe any media quickly
            attach_listeners(p)
            # Immediately close pop-ups/new tabs unless they start media; refocus main page
            try:
                p.wait_for_timeout(800)
            except Exception:
                pass
            try:
                if page_media_counts.get(p, 0) == 0:
                    p.close()
            except Exception:
                pass
            try:
                page.bring_to_front()
            except Exception:
                pass
            # After closing pop-up, try to trigger playback again on main page
            try:
                page.click("video", timeout=1500, force=True)
            except Exception:
                pass
            try:
                page.evaluate(
                    """
                    (() => {
                      const vids = Array.from(document.querySelectorAll('video'));
                      vids.forEach(v => { try { v.muted = true; v.autoplay = true; v.click(); const pr = v.play && v.play(); if (pr && pr.catch) pr.catch(()=>{}); } catch(e){} });
                      const btns = Array.from(document.querySelectorAll(
                        "button[aria-label*='play' i], .plyr__control[data-plyr='play'], .vjs-play-control, [class*='play']"
                      ));
                      btns.slice(0,3).forEach(b => { try { b.click(); } catch(e){} });
                    })();
                    """
                )
            except Exception:
                pass
            try:
                page.keyboard.press("Space")
            except Exception:
                pass

        context.on("page", on_new_page)

        # Step 1: Open URL
        page.goto(page_url, wait_until="domcontentloaded")
        
        # Step 2: Wait for ads to open in new tabs and handle them
        try:
            page.wait_for_timeout(3000)  # Wait for ads to potentially open
        except Exception:
            pass
            
        # Step 3: Close any ad tabs that opened (keep only main page)
        try:
            main_page = page
            for p in list(context.pages):
                if p != main_page:
                    try:
                        p.close()
                    except Exception:
                        pass
        except Exception:
            pass
            
        # Step 4: Reload the main page
        try:
            page.reload(wait_until="domcontentloaded")
        except Exception:
            pass
            
        # Step 5: Wait a moment after reload
        try:
            page.wait_for_timeout(2000)
        except Exception:
            pass

        # Helper: attempt to trigger playback with multiple common gestures
        def attempt_play(p):
            try:
                p.click("video", timeout=1500, force=True)
            except Exception:
                pass
            try:
                p.evaluate(
                    """
                    (() => {
                      const vids = Array.from(document.querySelectorAll('video'));
                      vids.forEach(v => {
                        try {
                          v.muted = true;
                          v.autoplay = true;
                          v.click();
                          v.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                          const pr = v.play && v.play();
                          if (pr && typeof pr.catch === 'function') { pr.catch(()=>{}); }
                        } catch(e){}
                      });

                      // Fluid Player controls
                      const fluidBtns = Array.from(document.querySelectorAll(".fluid_button.fluid_control_playpause, [data-tool='playpause']"));
                      fluidBtns.slice(0,3).forEach(b => { try { b.click(); } catch(e){} });

                      // Common containers
                      const containers = Array.from(document.querySelectorAll('.video-container, .fluid_video_wrapper, .mainplayer'));
                      containers.slice(0,3).forEach(c => { try { c.click(); } catch(e){} });

                      // Generic players
                      const btns = Array.from(document.querySelectorAll(
                        "button[aria-label*='play' i], .plyr__control[data-plyr='play'], .vjs-play-control, button, [class*='play']"
                      ));
                      btns.slice(0,5).forEach(b => { try { b.click(); } catch(e){} });
                    })();
                    """
                )
            except Exception:
                pass
            try:
                p.keyboard.press("Space")
            except Exception:
                pass

        # Step 6: Click on video after reload to trigger HLS requests
        try:
            page.bring_to_front()
        except Exception:
            pass
            
        # More aggressive video clicking after reload
        for attempt in range(3):
            try:
                # Try clicking video elements
                page.click("video", timeout=2000, force=True)
            except Exception:
                pass
            try:
                # Try clicking play buttons
                page.click("button[aria-label*='play' i], .plyr__control[data-plyr='play'], .vjs-play-control", timeout=1000, force=True)
            except Exception:
                pass
            try:
                # Execute comprehensive play script
                page.evaluate("""
                    (() => {
                        // Click all videos
                        const videos = document.querySelectorAll('video');
                        videos.forEach(v => {
                            try {
                                v.muted = true;
                                v.autoplay = true;
                                v.click();
                                v.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                if (v.play) v.play().catch(() => {});
                            } catch(e) {}
                        });
                        
                        // Click play buttons
                        const playButtons = document.querySelectorAll(
                            'button[aria-label*="play"], .play-button, .plyr__control[data-plyr="play"], .vjs-play-control, [class*="play"]'
                        );
                        playButtons.forEach(btn => {
                            try { btn.click(); } catch(e) {}
                        });
                        
                        // Click video containers
                        const containers = document.querySelectorAll('.video-container, .player, .video-player, .fluid_video_wrapper');
                        containers.forEach(c => {
                            try { c.click(); } catch(e) {}
                        });
                    })();
                """)
            except Exception:
                pass
            try:
                page.keyboard.press("Space")
            except Exception:
                pass
            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass
        # Close any extra pages that did not produce media and refocus main page
        try:
            for p2 in list(context.pages):
                if p2 is page:
                    continue
                if page_media_counts.get(p2, 0) == 0:
                    try:
                        p2.close()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            page.bring_to_front()
        except Exception:
            pass

        # Intercept for at least 12 seconds after attempting playback (first 5s for player start)
        try:
            page.wait_for_timeout(12000)
        except PlaywrightTimeoutError:
            pass
        # Then wait for remaining time if larger than 12s
        extra_ms = max(0, (timeout_seconds * 1000) - 12000)
        if extra_ms:
            try:
                page.wait_for_load_state("networkidle", timeout=extra_ms)
            except PlaywrightTimeoutError:
                pass

        # Construct a Cookie header from the context cookies
        cookies = context.cookies()
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies) if cookies else ""

        # Close API request context if created
        try:
            if api_ctx is not None:
                api_ctx.dispose()
        except Exception:
            pass
        context.close()
        browser.close()

    # Deduplicate by URL preserving order
    seen = set()
    uniq: List[dict] = []
    for it in found:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        uniq.append(it)

    return uniq, cookie_header