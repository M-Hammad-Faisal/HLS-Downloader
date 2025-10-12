import sys
import tempfile
import asyncio
import time
from pathlib import Path
import urllib.request
import urllib.parse
import signal
import base64

import aiohttp
from PyQt5 import QtCore, QtWidgets

from .utils import fetch_text, concat_ts, remux_to_mp4
from .hls import (
    parse_master_playlist,
    parse_media_playlist,
    select_variant,
    parse_resolution,
    download_all_segments,
)
from .capture import capture_media

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chromium/124.0.0.0 Safari/537.36"
)

SETTINGS_PATH = Path.cwd() / "hls_gui_settings.ini"



class HlsWorker(QtCore.QThread):
    """Worker thread for downloading HLS streams with progress tracking and cancellation support."""
    
    log = QtCore.pyqtSignal(str)
    percent = QtCore.pyqtSignal(int)
    finished_ok = QtCore.pyqtSignal(str)
    finished_err = QtCore.pyqtSignal(str)

    def __init__(self, url, out_path, res_text, bw, ua, ref, cookies, conc, remux, resource_type_hint=None, auth_hint=None):
        """Initialize the HLS worker with download parameters.
        
        Args:
            url: HLS playlist URL to download
            out_path: Output file path
            res_text: Desired resolution as text (e.g., "1920x1080")
            bw: Maximum bandwidth preference
            ua: User-Agent header value
            ref: Referer header value
            cookies: Cookie header value
            conc: Number of concurrent downloads
            remux: Whether to remux to MP4 format
            resource_type_hint: Hint about the resource type for headers
            auth_hint: Authorization header value
        """
        super().__init__()
        self.url = url
        self.out_path = Path(out_path)
        self.res_text = res_text
        self.bw = int(bw) if bw else None
        self.ua = ua or None
        self.ref = ref or None
        self.cookies = cookies or None
        self.conc = max(1, int(conc or 4))
        self.remux = bool(remux)
        self.resource_type_hint = resource_type_hint or None
        self.auth_hint = auth_hint or None
        self.cancel_flag = asyncio.Event()

    def cancel(self):
        """Request cancellation of the download operation."""
        self.log.emit("Cancel requested.")
        loop = getattr(self, "_loop", None)
        if loop:
            loop.call_soon_threadsafe(self.cancel_flag.set)
        else:
            self.cancel_flag.set()

    def run(self):
        """Run the HLS download operation in the worker thread."""
        try:
            asyncio.run(self._amain())
        except Exception as e:
            self.finished_err.emit(str(e))

    async def _amain(self):
        """Main async download logic for HLS streams."""
        headers = {}
        headers["User-Agent"] = self.ua or DEFAULT_UA
        if self.ref:
            headers["Referer"] = self.ref
            try:
                ref_o = urllib.parse.urlparse(self.ref)
                origin = f"{ref_o.scheme}://{ref_o.netloc}" if ref_o.scheme and ref_o.netloc else None
            except Exception:
                origin = None
        else:
            try:
                uo = urllib.parse.urlparse(self.url)
                origin = f"{uo.scheme}://{uo.netloc}" if uo.scheme and uo.netloc else None
            except Exception:
                origin = None
        if origin:
            headers["Origin"] = origin
        headers.setdefault("Accept", "*/*")
        headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        # Avoid brotli to keep environment simple
        headers.setdefault("Accept-Encoding", "gzip, deflate")
        headers.setdefault("Sec-Fetch-Dest", "empty")
        headers.setdefault("Sec-Fetch-Mode", "cors")
        # Compute Sec-Fetch-Site based on origin vs target URL
        try:
            target = urllib.parse.urlparse(self.url)
            site_val = "same-origin" if (origin and urllib.parse.urlparse(origin).netloc == target.netloc) else "cross-site"
        except Exception:
            site_val = "cross-site"
        headers.setdefault("Sec-Fetch-Site", site_val)
        if (self.resource_type_hint or "").lower() in ("xhr", "fetch"):
            headers.setdefault("X-Requested-With", "XMLHttpRequest")
        headers.setdefault("Connection", "keep-alive")
        if self.auth_hint:
            headers.setdefault("Authorization", self.auth_hint)
        if self.cookies:
            headers["Cookie"] = self.cookies

        # Debug: Log the headers being used for the request
        self.log.emit(f"🔍 Debug - Request headers:")
        for key, value in headers.items():
            # Truncate long values for readability
            display_value = value[:100] + "..." if len(value) > 100 else value
            self.log.emit(f"  {key}: {display_value}")

        self._loop = asyncio.get_running_loop()
        self.out_path.parent.mkdir(parents=True, exist_ok=True)

        timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
        conn = aiohttp.TCPConnector(limit=20)
        async with aiohttp.ClientSession(timeout=timeout, connector=conn) as session:
            self.log.emit("[1/5] Fetching playlist…")
            text = await fetch_text(session, self.url, headers)

            base = self.url
            if "#EXT-X-STREAM-INF" in text:
                self.log.emit("[2/5] Master playlist detected. Selecting variant…")
                variants = parse_master_playlist(text, base)
                if not variants:
                    raise RuntimeError("No variants found in master playlist.")
                want_res = parse_resolution(self.res_text) if self.res_text else None
                chosen = select_variant(variants, want_res=want_res, want_bw=self.bw)
                self.log.emit(f"Chosen: {chosen.resolution or 'unknown'} @ {chosen.bandwidth or 'n/a'} → {chosen.uri}")
                text = await fetch_text(session, chosen.uri, headers)
                base = chosen.uri
            else:
                self.log.emit("[2/5] Media playlist detected.")

            if "EXT-X-KEY" in text and "METHOD=SAMPLE-AES" in text:
                raise RuntimeError("DRM detected (SAMPLE-AES). This app does not support DRM.")

            self.log.emit("[3/5] Parsing segments…")
            segments = parse_media_playlist(text, base)
            if not segments:
                raise RuntimeError("No segments found in playlist.")

            self.log.emit(f"[4/5] Downloading {len(segments)} segments (concurrency={self.conc})…")
            last_pct = -1

            def progress_fn(done, total_):
                nonlocal last_pct
                pct = int(done / total_ * 100)
                if pct != last_pct:
                    self.percent.emit(pct)
                    last_pct = pct

            with tempfile.TemporaryDirectory() as tmpdir:
                temp_dir = Path(tmpdir)
                paths = await download_all_segments(session, segments, headers, self.conc, temp_dir, self.log.emit, progress_fn, self.cancel_flag)
                if self.cancel_flag.is_set():
                    self.finished_err.emit("Cancelled")
                    return

                self.log.emit("[5/5] Concatenating segments…")
                merged_ts = temp_dir / "merged.ts"
                concat_ts(paths, merged_ts)

                if self.remux:
                    final_mp4 = self.out_path if self.out_path.suffix.lower() == ".mp4" else self.out_path.with_suffix(".mp4")
                    remux_to_mp4(merged_ts, final_mp4, self.log.emit)
                    self.percent.emit(100)
                    self.finished_ok.emit(str(final_mp4))
                else:
                    final_ts = self.out_path if self.out_path.suffix.lower() == ".ts" else self.out_path.with_suffix(".ts")
                    final_ts.write_bytes(merged_ts.read_bytes())
                    self.percent.emit(100)
                    self.finished_ok.emit(str(final_ts))


class CaptureWorker(QtCore.QThread):
    """Worker thread for capturing media URLs from web pages using Playwright."""
    
    captured = QtCore.pyqtSignal(list, str)
    error = QtCore.pyqtSignal(str)

    def __init__(self, page_url: str, headers: dict, headless: bool, timeout_seconds: int = 30):
        """Initialize the capture worker with page parameters.
        
        Args:
            page_url: URL of the web page to capture from
            headers: HTTP headers to use when loading the page
            headless: Whether to run browser in headless mode
            timeout_seconds: Maximum time to wait for media capture
        """
        super().__init__()
        self.page_url = page_url
        self.headers = headers or {}
        self.headless = bool(headless)
        self.timeout_seconds = int(timeout_seconds)

    def run(self):
        """Run the media capture operation in the worker thread."""
        try:
            items, cookie_header = capture_media(
                self.page_url,
                headers=self.headers,
                headless=self.headless,
                timeout_seconds=self.timeout_seconds,
                verbose=False,
                include_m3u8_body=True,
            )
            self.captured.emit(items, cookie_header)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QtWidgets.QWidget):
    """Main GUI window for the HLS downloader application."""
    
    def __init__(self):
        """Initialize the main window with UI components and settings."""
        super().__init__()
        self.setWindowTitle("HLS Downloader (Legal Streams Only)")
        self.resize(780, 580)  # Optimized for 800x600 screens
        self.worker = None
        self.cap_worker = None
        self.captured_items = []
        self.captured_cookie = ""
        self.variant_uris = []
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        """Build and layout the main user interface components in a single page layout."""
        L = QtWidgets.QVBoxLayout(self)
        
        # Build all components in a single layout
        self._build_single_page_layout(L)
        
        # Common controls at bottom
        self._build_common_controls(L)

    def _build_single_page_layout(self, main_layout):
        """Build all UI components in a single page layout."""
        # Page URL input
        row_pg = QtWidgets.QHBoxLayout()
        row_pg.addWidget(QtWidgets.QLabel("Page URL:"))
        self.page_in = QtWidgets.QLineEdit()
        self.page_in.setPlaceholderText("Enter the web page URL that plays the video")
        self.page_in.textChanged.connect(self._on_page_url_changed)
        row_pg.addWidget(self.page_in, 1)
        main_layout.addLayout(row_pg)
        
        # Capture options
        row_opts = QtWidgets.QHBoxLayout()
        self.headless_cb = QtWidgets.QCheckBox("Show Browser (uncheck for background capture)")
        self.headless_cb.setChecked(False)  # Default to headless (background) capture
        row_opts.addWidget(self.headless_cb)
        
        # Set default timeout internally (60 seconds)
        self.cap_timeout = QtWidgets.QSpinBox()
        self.cap_timeout.setValue(60)  # Hidden, default to 60 seconds
        
        self.btn_capture = QtWidgets.QPushButton("Open & Capture")
        self.btn_capture.clicked.connect(self._start_capture)
        row_opts.addWidget(self.btn_capture)
        main_layout.addLayout(row_opts)
        
        # Captured items list
        main_layout.addWidget(QtWidgets.QLabel("Captured Media:"))
        self.capture_list = QtWidgets.QListWidget()
        self.capture_list.setMinimumHeight(120)
        main_layout.addWidget(self.capture_list)
        
        # Keep buttons as internal variables for backend functionality but don't add to UI
        self.btn_copy_selected = QtWidgets.QPushButton("Copy URL")
        self.btn_copy_selected.setEnabled(True)
        self.btn_copy_selected.clicked.connect(self._copy_selected_url)
        self.btn_copy_selected.setVisible(False)
        
        self.btn_apply_headers = QtWidgets.QPushButton("Apply Headers")
        self.btn_apply_headers.setEnabled(True)
        self.btn_apply_headers.clicked.connect(self._apply_captured_headers)
        self.btn_apply_headers.setVisible(False)
        
        # Resolution selection
        res_group = QtWidgets.QGroupBox("Resolution Selection")
        res_layout = QtWidgets.QVBoxLayout(res_group)
        
        row_res = QtWidgets.QHBoxLayout()
        row_res.addWidget(QtWidgets.QLabel("Resolution:"))
        self.variant_combo = QtWidgets.QComboBox()
        self.variant_combo.setEnabled(False)
        self.variant_combo.currentIndexChanged.connect(self._on_resolution_selected)
        row_res.addWidget(self.variant_combo, 1)
        res_layout.addLayout(row_res)
        
        self.btn_use_variant = QtWidgets.QPushButton("Use selected resolution")
        self.btn_use_variant.setEnabled(False)
        self.btn_use_variant.clicked.connect(self._use_selected_variant)
        self.btn_use_variant.setVisible(False)
        
        main_layout.addWidget(res_group)
        
        # Output file section
        row_out = QtWidgets.QHBoxLayout()
        row_out.addWidget(QtWidgets.QLabel("Output file:"))
        self.out_in = QtWidgets.QLineEdit(str(Path.cwd() / "downloads" / "output.mp4"))
        row_out.addWidget(self.out_in, 1)
        btn_browse = QtWidgets.QPushButton("Browse…")
        btn_browse.clicked.connect(self._choose_output)
        row_out.addWidget(btn_browse)
        main_layout.addLayout(row_out)
        
        # Keep internal variables for headers and other settings but don't show UI fields
        self.url_in = QtWidgets.QLineEdit()  # Hidden, for internal use only
        self.ua_in = QtWidgets.QLineEdit()  # Hidden, will use defaults
        self.ref_in = QtWidgets.QLineEdit()  # Hidden, will use defaults  
        self.cookies_in = QtWidgets.QLineEdit()  # Hidden, will use defaults
        self.conc_in = QtWidgets.QLineEdit("4")  # Hidden, hardcoded to 4
        self.remux_cb = QtWidgets.QCheckBox()  # Hidden, always enabled
        self.remux_cb.setChecked(True)
        
        # Download button
        self.btn_download_selected = QtWidgets.QPushButton("Download Selected Resolution")
        self.btn_download_selected.setEnabled(False)
        self.btn_download_selected.clicked.connect(self._download_selected)
        main_layout.addWidget(self.btn_download_selected)
        
        # Alias for compatibility with existing code
        self.btn_start = self.btn_download_selected
        
        # Remember inputs
        self.remember_cb = QtWidgets.QCheckBox("Remember inputs")
        self.remember_cb.setChecked(True)
        main_layout.addWidget(self.remember_cb)
        
        # Double-click captured item to copy URL
        try:
            self.capture_list.itemDoubleClicked.connect(lambda _: self._copy_selected_url())
        except Exception:
            pass

    def _build_common_controls(self, main_layout):
        """Build common controls that appear at the bottom."""
        # Progress bar
        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        main_layout.addWidget(self.pbar)
        
        # Status
        self.status = QtWidgets.QLabel("Status: idle")
        main_layout.addWidget(self.status)
        
        # Log (compact)
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)  # Limit height for 800x600
        main_layout.addWidget(self.log)
        
        # Cancel button (for stopping ongoing downloads)
        self.btn_cancel = QtWidgets.QPushButton("Cancel Download")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        main_layout.addWidget(self.btn_cancel)
        
        note = QtWidgets.QLabel(
            "Use only for NON-DRM streams you are authorized to save."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 10px; color: gray;")
        main_layout.addWidget(note)

    def _choose_output(self):
        """Choose output file location."""
        current = self.out_in.text().strip()
        if not current:
            current = str(Path.cwd() / "downloads" / "output.mp4")
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save As", current, "Video Files (*.mp4 *.ts);;All Files (*)"
        )
        if path:
            self.out_in.setText(path)

    def _copy_selected_url(self):
        """Copy the selected captured URL to clipboard."""
        try:
            idx = self.capture_list.currentRow()
            if idx < 0 or idx >= len(self.captured_items):
                QtWidgets.QMessageBox.information(self, "Copy URL", "Select an item first.")
                return
            url = self.captured_items[idx].get("url") or ""
            if not url:
                QtWidgets.QMessageBox.information(self, "Copy URL", "Selected item has no URL.")
                return
            QtWidgets.QApplication.clipboard().setText(url)
            self.status.setText("Copied URL to clipboard")
        except Exception:
            QtWidgets.QMessageBox.information(self, "Copy URL", "Could not copy URL.")

    def _apply_captured_headers(self):
        """Apply headers from the selected captured request."""
        try:
            idx = self.capture_list.currentRow()
            if idx < 0 or idx >= len(self.captured_items):
                QtWidgets.QMessageBox.information(self, "Apply Headers", "Select an item first.")
                return
            
            item = self.captured_items[idx]
            headers = item.get("headers", {})
            
            ua = headers.get("User-Agent") or headers.get("user-agent")
            if ua:
                self.ua_in.setText(ua)
            
            referer = headers.get("Referer") or headers.get("referer")
            if referer:
                self.ref_in.setText(referer)
            
            auth = headers.get("Authorization") or headers.get("authorization")
            if auth:
                current_cookies = self.cookies_in.text().strip()
                if "Authorization:" not in current_cookies:
                    if current_cookies and not current_cookies.endswith("; "):
                        current_cookies += "; "
                    current_cookies += f"Authorization: {auth}"
                    self.cookies_in.setText(current_cookies)
            
            cookie_header = item.get("cookie_header", "")
            if cookie_header and cookie_header != self.cookies_in.text().strip():
                self.cookies_in.setText(cookie_header)
            
            self.status.setText("Applied headers from selected request")
            
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Apply Headers", f"Could not apply headers: {e}")

    def _on_resolution_selected(self, index):
        """Handle resolution selection from dropdown."""
        if index < 0 or not hasattr(self, 'variant_uris') or index >= len(self.variant_uris):
            return
            
        try:
            selected_url = self.variant_uris[index]
            resolution_text = self.variant_combo.itemText(index)
            
            if index == 0 and selected_url == "":
                self.btn_download_selected.setEnabled(False)
                self.status.setText("Please select a resolution")
                return
            
            self.url_in.setText(selected_url)
            self._auto_generate_output_path()
            self._auto_apply_headers_for_url(selected_url)
            
            self.status.setText(f"Selected resolution: {resolution_text}")
            self._append(f"✅ Auto-selected resolution: {resolution_text}")
            self.btn_download_selected.setEnabled(True)
            
        except Exception as e:
            self._append(f"❌ Error selecting resolution: {e}")

    def _auto_apply_headers_for_url(self, url):
        """Automatically apply the best matching headers for the given URL."""
        try:
            if not hasattr(self, 'captured_items') or not self.captured_items:
                return
                
            best_match = None
            url_lower = url.lower()
            
            for item in self.captured_items:
                item_url = (item.get("url") or "").lower()
                if item_url == url_lower or (item_url.endswith(".m3u8") and url_lower.endswith(".m3u8")):
                    best_match = item
                    break
            
            if not best_match:
                for item in self.captured_items:
                    if item.get("url", "").lower().endswith(".m3u8") and item.get("headers"):
                        best_match = item
                        break
            
            if best_match:
                headers = best_match.get("headers", {})
                
                ua = headers.get("User-Agent") or headers.get("user-agent")
                if ua:
                    self.ua_in.setText(ua)
                
                referer = headers.get("Referer") or headers.get("referer")
                if referer:
                    self.ref_in.setText(referer)
                
                cookie_header = best_match.get("cookie_header", "")
                if cookie_header:
                    self.cookies_in.setText(cookie_header)
                
                self._append("🔧 Headers automatically applied")
                
        except Exception as e:
            self._append(f"⚠️ Could not auto-apply headers: {e}")

    def _auto_generate_output_path(self):
        """Auto-generate output file path based on page URL."""
        try:
            page_url = self.page_in.text().strip()
            
            if page_url:
                derived_path = self._derive_nested_output(page_url)
                self.out_in.setText(str(derived_path.resolve()))
            else:
                default_path = str(Path.cwd() / "downloads" / "output.mp4")
                self.out_in.setText(default_path)
                
        except Exception as e:
            self._append(f"⚠️ Could not auto-generate output path: {e}")

    def _on_page_url_changed(self):
        """Handle page URL changes to auto-generate output file paths."""
        if hasattr(self, '_loading_settings') and self._loading_settings:
            return
        self._auto_generate_output_path()

    def _derive_nested_output(self, url: str) -> Path:
        """Generate a nested output path based on the URL structure."""
        downloads_dir = Path.cwd() / "downloads"
        try:
            u = urllib.parse.urlparse(url)
            netloc = u.netloc or "unknown-host"

            def sanitize(s: str) -> str:
                s2 = "".join(c for c in s if c.isalnum() or c in ("-", "_", "."))
                return (s2 or "_")[:64]

            base = downloads_dir / sanitize(netloc)
            segs = [sanitize(seg) for seg in (u.path or "").split("/") if seg]
            if not segs:
                segs = ["video"]
            
            stem = segs[-1]
            lower = stem.lower()
            if lower.endswith((".m3u8", ".mp4", ".ts")):
                stem = stem[:stem.rfind(".")]
            
            nested_dir = base.joinpath(*segs[:-1]) if len(segs) > 1 else base
            return nested_dir / f"{stem}.mp4"
        except Exception:
            return downloads_dir / "output.mp4"







    def _download_selected(self):
        """Download the currently selected resolution."""
        self._start()





    def _start(self):
        """Start the HLS download process with current settings."""
        url = self.url_in.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "Missing URL", "Capture a page and select a resolution to fill the variant URL.")
            return
        out_path = self.out_in.text().strip()
        # Auto-derive output if default/blank
        default_out = str(Path.cwd() / "downloads" / "output.mp4")
        if not out_path or out_path == default_out:
            try:
                # Use the original page URL for file path generation instead of variant URL
                page_url = self.page_in.text().strip()
                if page_url:
                    derived = self._derive_nested_output(page_url)
                else:
                    derived = self._derive_nested_output(url)
                if not self.remux_cb.isChecked() and derived.suffix.lower() == ".mp4":
                    derived = derived.with_suffix(".ts")
                out_path = str(derived.resolve())
                self.out_in.setText(out_path)
                self._append(f"Output auto-set: {out_path}")
            except Exception:
                pass
        if not out_path:
            QtWidgets.QMessageBox.warning(self, "Missing Output", "Please choose an output file path.")
            return

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.pbar.setValue(0)
        self.status.setText("Starting…")
        self.log.clear()
        self._append(f"Queued: {url}\nSaving to: {out_path}")

        # Check if captured data is fresh (within 5 minutes)
        current_time = time.time()
        oldest_capture = None
        for item in getattr(self, "captured_items", []) or []:
            capture_time = item.get("capture_timestamp")
            if capture_time:
                if oldest_capture is None or capture_time < oldest_capture:
                    oldest_capture = capture_time
        
        if oldest_capture and (current_time - oldest_capture) > 300:  # 5 minutes = 300 seconds
            minutes_old = int((current_time - oldest_capture) / 60)
            self._append(f"⚠️  Warning: Captured data is {minutes_old} minutes old. Consider re-capturing for fresh tokens.")

        # Prefer intercepted Referer for the selected URL; override any manual value if found
        ref = self.ref_in.text().strip()
        try:
            captured_ref = None
            target_host = None
            try:
                target_host = urllib.parse.urlparse(url).netloc
            except Exception:
                target_host = None
            # Prefer exact match to selected URL
            for it in getattr(self, "captured_items", []) or []:
                if it.get("kind") != "request":
                    continue
                ureq = it.get("url") or ""
                if ureq == url:
                    hdrs = it.get("headers") or {}
                    captured_ref = hdrs.get("referer") or hdrs.get("Referer") or it.get("page_url") or it.get("frame_url") or None
                    if captured_ref:
                        break
            # Else any request on same host
            if not captured_ref and target_host:
                for it in getattr(self, "captured_items", []) or []:
                    if it.get("kind") != "request":
                        continue
                    try:
                        host = urllib.parse.urlparse(it.get("url") or "").netloc
                    except Exception:
                        host = None
                    if host and host == target_host:
                        hdrs = it.get("headers") or {}
                        captured_ref = hdrs.get("referer") or hdrs.get("Referer") or it.get("page_url") or it.get("frame_url") or None
                        if captured_ref:
                            break
            if captured_ref:
                ref = captured_ref
                self.ref_in.setText(captured_ref)
        except Exception:
            pass
        # Fallback to page URL if still empty
        ref = ref or self.page_in.text().strip()
        ua = self.ua_in.text().strip() or DEFAULT_UA
        # Infer resource type from capture for better headers
        rtype = None
        auth_hint = None
        url_low = url.lower()
        for it in getattr(self, "captured_items", []) or []:
            if it.get("kind") == "request":
                ureq = (it.get("url") or "").lower()
                if ureq == url_low or (ureq.endswith(".m3u8") and url_low.endswith(".m3u8")):
                    rtype = (it.get("resource_type") or "").lower() or None
                    hdrs = it.get("headers") or {}
                    auth_hint = hdrs.get("authorization") or hdrs.get("Authorization") or None
                    break
        # Get selected resolution information
        res_text = None
        bw = None
        if hasattr(self, 'variant_combo') and self.variant_combo.currentIndex() >= 0:
            current_index = self.variant_combo.currentIndex()
            res_text = self.variant_combo.itemText(current_index)
            # Extract bandwidth if available in the resolution text
            if hasattr(self, 'variant_bandwidths') and current_index < len(self.variant_bandwidths):
                bw = self.variant_bandwidths[current_index]
        
        self.worker = HlsWorker(
            url=url,
            out_path=out_path,
            res_text=res_text,
            bw=bw,
            ua=ua,
            ref=ref,
            cookies=self.cookies_in.text().strip(),
            conc=self.conc_in.text().strip(),
            remux=self.remux_cb.isChecked(),
            resource_type_hint=rtype,
            auth_hint=auth_hint,
        )
        self.worker.log.connect(self._append)
        self.worker.percent.connect(self._on_percent)
        self.worker.finished_ok.connect(self._on_ok)
        self.worker.finished_err.connect(self._on_err)
        self.worker.start()

    def _cancel(self):
        """Cancel the currently running download operation."""
        if self.worker:
            self.worker.cancel()

    def _start_capture(self):
        """Start capturing media URLs from the specified web page."""
        page_url = self.page_in.text().strip()
        if not page_url:
            QtWidgets.QMessageBox.warning(self, "Missing Page URL", "Enter a page URL to open and capture.")
            return
        headers = {}
        ua = self.ua_in.text().strip() or DEFAULT_UA
        ref = self.ref_in.text().strip() or page_url
        # reflect effective values back into the UI so you see them
        self.ua_in.setText(ua)
        self.ref_in.setText(ref)
        ck = self.cookies_in.text().strip()
        headers["User-Agent"] = ua
        headers["Referer"] = ref
        if ck:
            headers["Cookie"] = ck
        self.status.setText("Capturing…")
        self.capture_list.clear()
        self.variant_combo.clear()
        self.variant_combo.setEnabled(False)
        self.btn_use_variant.setEnabled(False)
        self.btn_download_selected.setEnabled(False)
        self.captured_items = []
        self.captured_cookie = ""

        # Run capture in a thread
        self.btn_capture.setEnabled(False)
        # Invert the checkbox logic: unchecked = headless (background), checked = show browser
        headless_mode = not self.headless_cb.isChecked()
        self.cap_worker = CaptureWorker(page_url, headers, headless_mode, self.cap_timeout.value())
        self.cap_worker.captured.connect(self._on_captured)
        self.cap_worker.error.connect(self._on_capture_err)
        self.cap_worker.start()

    @QtCore.pyqtSlot(list, str)
    def _on_captured(self, items, cookie_header):
        self.status.setText("Captured")
        self.btn_capture.setEnabled(True)
        
        capture_time = time.time()
        for item in items:
            item["capture_timestamp"] = capture_time
            
        self.captured_items = items
        self.captured_cookie = cookie_header or ""
        if not self.cookies_in.text().strip() and self.captured_cookie:
            self.cookies_in.setText(self.captured_cookie)
        
        try:
            captured_ref = None
            for it in items:
                if it.get("kind") == "request":
                    hdrs = it.get("headers") or {}
                    captured_ref = hdrs.get("referer") or hdrs.get("Referer") or captured_ref
                    if captured_ref:
                        break
            if captured_ref:
                self.ref_in.setText(captured_ref)
        except Exception:
            pass
        
        for it in items:
            ct = it.get("content_type") or ""
            self.capture_list.addItem(f"[{it['kind']}] {it['url']} {ct}")
        
        master_body = None
        master_url = None
        
        for it in items:
            u = it.get("url", "")
            b = it.get("body") or ""
            if b and "#EXT-X-STREAM-INF" in b:
                master_body = b
                master_url = u
                break
        
        if not master_body:
            candidates = []
            for it in items:
                u = it.get("url", "").lower()
                if u.endswith(".m3u8"):
                    candidates.append(it.get("url"))
            
            for candidate in candidates:
                if candidate:
                    captured_ref = None
                    captured_origin = None
                    captured_rtype = None
                    for it in items:
                        if it.get("kind") == "request":
                            u_low = (it.get("url") or "").lower()
                            if u_low == candidate.lower() or ".m3u8" in u_low:
                                h = it.get("headers") or {}
                                captured_ref = h.get("referer") or h.get("Referer") or captured_ref
                                captured_origin = h.get("origin") or h.get("Origin") or captured_origin
                                captured_rtype = it.get("resource_type") or captured_rtype
                                if u_low == candidate.lower():
                                    break
                    try:
                        hdrs = {}
                        hdrs["User-Agent"] = self.ua_in.text().strip() or DEFAULT_UA
                        ref_val = captured_ref or self.ref_in.text().strip() or self.page_in.text().strip()
                        if ref_val:
                            self.ref_in.setText(ref_val)
                        if ref_val:
                            hdrs["Referer"] = ref_val
                            try:
                                if captured_origin:
                                    origin = captured_origin
                                else:
                                    ro = urllib.parse.urlparse(ref_val)
                                    origin = f"{ro.scheme}://{ro.netloc}" if ro.scheme and ro.netloc else None
                            except Exception:
                                origin = None
                            if origin:
                                hdrs["Origin"] = origin
                        
                        try:
                            cu = urllib.parse.urlparse(candidate)
                            on = urllib.parse.urlparse(origin).netloc if origin else None
                            site_val = "same-origin" if (on and cu.netloc == on) else "cross-site"
                        except Exception:
                            site_val = "cross-site"
                        hdrs.setdefault("Accept", "*/*")
                        hdrs.setdefault("Accept-Language", "en-US,en;q=0.9")
                        hdrs.setdefault("Accept-Encoding", "gzip, deflate")
                        hdrs.setdefault("Sec-Fetch-Dest", "empty")
                        hdrs.setdefault("Sec-Fetch-Mode", "cors")
                        hdrs.setdefault("Sec-Fetch-Site", site_val)
                        
                        try:
                            ch = h if 'h' in locals() else {}
                            sec_ch_ua = ch.get("sec-ch-ua") or ch.get("Sec-CH-UA") or "\"Chromium\";v=124, \"Not.A/Brand\";v=24"
                            sec_ch_platform = ch.get("sec-ch-ua-platform") or ch.get("Sec-CH-UA-Platform") or "\"macOS\""
                            sec_ch_mobile = ch.get("sec-ch-ua-mobile") or ch.get("Sec-CH-UA-Mobile") or "?0"
                        except Exception:
                            sec_ch_ua, sec_ch_platform, sec_ch_mobile = None, None, None
                        if sec_ch_ua:
                            hdrs.setdefault("Sec-CH-UA", sec_ch_ua)
                        if sec_ch_platform:
                            hdrs.setdefault("Sec-CH-UA-Platform", sec_ch_platform)
                        if sec_ch_mobile:
                            hdrs.setdefault("Sec-CH-UA-Mobile", sec_ch_mobile)
                        if captured_rtype in ("xhr", "fetch"):
                            hdrs.setdefault("X-Requested-With", "XMLHttpRequest")
                        
                        try:
                            auth = (h.get("authorization") or h.get("Authorization") if 'h' in locals() else None)
                        except Exception:
                            auth = None
                        if auth:
                            hdrs["Authorization"] = auth
                        ck = self.cookies_in.text().strip() or self.captured_cookie
                        if ck:
                            hdrs["Cookie"] = ck
                        req = urllib.request.Request(candidate, headers=hdrs)
                        with urllib.request.urlopen(req, timeout=30) as r:
                            master_body = r.read().decode("utf-8", errors="ignore")
                            master_url = candidate
                            break
                    except Exception as e:
                        self._append(f"Failed to fetch master playlist from {candidate}: {e}")
                        continue
        if master_body and master_url:
            variants = parse_master_playlist(master_body, master_url)
            if variants:
                self.variant_combo.setEnabled(True)
                self.btn_use_variant.setEnabled(True)
                self.btn_download_selected.setEnabled(False)
                self.variant_combo.clear()
                self.variant_uris = []
                
                self.variant_combo.addItem("Select a resolution")
                self.variant_uris.append("")
                
                sorted_variants = sorted(variants, key=lambda v: v.bandwidth or 0, reverse=True)
                
                for v in sorted_variants:
                    resolution = v.resolution or 'Unknown'
                    bandwidth = v.bandwidth
                    if bandwidth:
                        bandwidth_mbps = round(bandwidth / 1000000, 1)
                        label = f"{resolution} ({bandwidth_mbps} Mbps)"
                    else:
                        label = f"{resolution}"
                    
                    self.variant_combo.addItem(label)
                    self.variant_uris.append(v.uri)
                
                self.variant_combo.setCurrentIndex(0)
                self._append(f"🎯 Found {len(sorted_variants)} resolutions. Please select your preferred resolution from the dropdown above.")
            else:
                self._append("No variants found in master playlist.")
        else:
            try:
                m3u8_urls = []
                for it in items:
                    u = (it.get("url") or "").lower()
                    if u.endswith(".m3u8"):
                        m3u8_urls.append(it.get("url"))
                
                def infer_label(u: str) -> str:
                    try:
                        path_segs = [seg for seg in (urllib.parse.urlparse(u).path or "").split("/") if seg]
                        for seg in path_segs:
                            try:
                                dec = base64.b64decode(seg + "==" if len(seg) % 4 != 0 else seg).decode("utf-8", errors="ignore")
                                dec2 = "".join(ch for ch in dec if ch.isdigit())
                                if dec2.isdigit():
                                    return dec2
                            except Exception:
                                pass
                        for seg in path_segs:
                            if seg.isdigit():
                                return seg
                    except Exception:
                        pass
                    return "unknown"

                derived = [(infer_label(u), u) for u in m3u8_urls]
                def sort_key(t):
                    lbl = t[0]
                    return -(int(lbl) if lbl.isdigit() else -1)
                derived.sort(key=sort_key)

                if derived:
                    self.variant_combo.setEnabled(True)
                    self.btn_use_variant.setEnabled(True)
                    self.btn_download_selected.setEnabled(False)
                    self.variant_combo.clear()
                    self.variant_uris = []
                    
                    self.variant_combo.addItem("Select a resolution")
                    self.variant_uris.append("")
                    
                    for lbl, u in derived:
                        label = f"{lbl if lbl != 'unknown' else 'unknown'}"
                        self.variant_combo.addItem(label)
                        self.variant_uris.append(u)
                    self._append("Variants inferred from captured URLs. Please select one from the dropdown above.")
                else:
                    self._append("No master playlist found. Click play and try capture again.")
            except Exception:
                self._append("No master playlist found. Click play and try capture again.")

    @QtCore.pyqtSlot(str)
    def _on_capture_err(self, msg):
        self.status.setText("Capture error")
        self._append(f"❌ Capture error: {msg}")
        self.btn_capture.setEnabled(True)

    def _use_selected_variant(self):
        idx = self.variant_combo.currentIndex()
        if idx < 0 or idx >= len(self.variant_uris):
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select a resolution from the list.")
            return
        chosen_uri = self.variant_uris[idx]
        self.url_in.setText(chosen_uri)
        
        try:
            cap_ref = None
            for it in getattr(self, "captured_items", []) or []:
                if it.get("kind") == "request" and (it.get("url") or "") == chosen_uri:
                    hdrs = it.get("headers") or {}
                    cap_ref = hdrs.get("referer") or hdrs.get("Referer") or it.get("page_url") or it.get("frame_url") or None
                    if cap_ref:
                        break
            if not cap_ref:
                try:
                    target_host = urllib.parse.urlparse(chosen_uri).netloc
                except Exception:
                    target_host = None
                for it in getattr(self, "captured_items", []) or []:
                    if it.get("kind") != "request":
                        continue
                    try:
                        host = urllib.parse.urlparse(it.get("url") or "").netloc
                    except Exception:
                        host = None
                    if host and target_host and host == target_host:
                        hdrs = it.get("headers") or {}
                        cap_ref = hdrs.get("referer") or hdrs.get("Referer") or it.get("page_url") or it.get("frame_url") or None
                        if cap_ref:
                            break
            if cap_ref:
                self.ref_in.setText(cap_ref)
        except Exception:
            pass
        
        default_out = str(Path.cwd() / "downloads" / "output.mp4")
        cur_out = self.out_in.text().strip()
        if not cur_out or cur_out == default_out:
            try:
                page_url = self.page_in.text().strip()
                if page_url:
                    derived = self._derive_nested_output(page_url)
                else:
                    derived = self._derive_nested_output(chosen_uri)
                self.out_in.setText(str(derived.resolve()))
            except Exception:
                pass
        self._append(f"Selected variant URL set: {chosen_uri}")

    def _download_selected(self):
        self._use_selected_variant()
        self._start()

    def _load_settings(self):
        self._loading_settings = True
        try:
            s = QtCore.QSettings(str(SETTINGS_PATH), QtCore.QSettings.IniFormat)
            self.url_in.setText(s.value("url", ""))
            self.out_in.setText(s.value("out", str(Path.cwd() / "downloads" / "output.mp4")))
            self.ua_in.setText(s.value("ua", DEFAULT_UA))
            self.ref_in.setText(s.value("ref", ""))
            self.cookies_in.setText(s.value("cookies", ""))
            self.conc_in.setText("4")
            self.remux_cb.setChecked(bool(s.value("remux", True, type=bool)))
            self.page_in.setText(s.value("page", ""))
            self.headless_cb.setChecked(bool(s.value("headless", False, type=bool)))
            self.cap_timeout.setValue(int(s.value("cap_timeout", 30)))
            self.remember_cb.setChecked(bool(s.value("remember", True, type=bool)))
        finally:
            self._loading_settings = False

    def closeEvent(self, e):
        if self.remember_cb.isChecked():
            s = QtCore.QSettings(str(SETTINGS_PATH), QtCore.QSettings.IniFormat)
            s.setValue("url", self.url_in.text())
            s.setValue("out", self.out_in.text())
            s.setValue("ua", self.ua_in.text())
            s.setValue("ref", self.ref_in.text())
            s.setValue("cookies", self.cookies_in.text())
            s.setValue("conc", self.conc_in.text())
            s.setValue("remux", self.remux_cb.isChecked())
            s.setValue("page", self.page_in.text())
            s.setValue("headless", self.headless_cb.isChecked())
            s.setValue("cap_timeout", self.cap_timeout.value())
            s.setValue("remember", self.remember_cb.isChecked())
        super().closeEvent(e)

    @QtCore.pyqtSlot(str)
    def _append(self, s: str):
        self.log.append(s)
        QtCore.QTimer.singleShot(0, self.log.ensureCursorVisible)

    @QtCore.pyqtSlot(int)
    def _on_percent(self, p: int):
        self.pbar.setValue(p)
        self.status.setText(f"Downloading — {p}%")

    @QtCore.pyqtSlot(str)
    def _on_ok(self, path: str):
        self._append(f"✅ Saved: {path}")
        self.status.setText("Completed")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.pbar.setValue(100)

    @QtCore.pyqtSlot(str)
    def _on_err(self, msg: str):
        self._append(f"❌ Error: {msg}")
        self.status.setText("Error")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    try:
        signal.signal(signal.SIGINT, lambda *args: QtWidgets.QApplication.quit())
    except Exception:
        pass
    tick = QtCore.QTimer()
    tick.start(250)
    tick.timeout.connect(lambda: None)
    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        try:
            w.close()
        except Exception:
            pass
        QtWidgets.QApplication.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()