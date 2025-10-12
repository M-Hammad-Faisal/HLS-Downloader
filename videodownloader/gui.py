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


class EpisodeDiscoveryWorker(QtCore.QThread):
    """Worker thread for discovering episodes without blocking the UI."""
    episodes_found = QtCore.pyqtSignal(list, str)  # episodes, original_url
    discovery_error = QtCore.pyqtSignal(str)  # error_message
    
    def __init__(self, url, gui_instance):
        """Initialize the episode discovery worker.
        
        Args:
            url: The base URL to discover episodes from
            gui_instance: Reference to the main GUI instance for accessing methods
        """
        super().__init__()
        self.url = url
        self.gui_instance = gui_instance
    
    def run(self):
        """Run episode discovery in background thread."""
        try:
            episodes = self.gui_instance._parse_episode_urls(self.url)
            self.episodes_found.emit(episodes, self.url)
        except Exception as e:
            self.discovery_error.emit(str(e))


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
            total = len(segments)
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
        """Build and layout the main user interface components with tabbed interface for 800x600 screens."""
        L = QtWidgets.QVBoxLayout(self)
        
        self.tab_widget = QtWidgets.QTabWidget()
        L.addWidget(self.tab_widget)
        
        # Tab 1: Capture & Setup
        self._build_capture_tab()
        
        # Tab 2: Download Settings
        self._build_download_tab()
        
        # Tab 3: Episodes & Batch
        self._build_episodes_tab()
        
        # Common controls at bottom
        self._build_common_controls(L)

    def _build_capture_tab(self):
        """Build the capture and setup tab."""
        capture_widget = QtWidgets.QWidget()
        L = QtWidgets.QVBoxLayout(capture_widget)
        
        # Page URL input
        row_pg = QtWidgets.QHBoxLayout()
        row_pg.addWidget(QtWidgets.QLabel("Page URL:"))
        self.page_in = QtWidgets.QLineEdit()
        self.page_in.setPlaceholderText("Enter the web page URL that plays the video")
        self.page_in.textChanged.connect(self._on_page_url_changed)
        row_pg.addWidget(self.page_in, 1)
        L.addLayout(row_pg)
        
        # Capture options
        row_opts = QtWidgets.QHBoxLayout()
        self.headless_cb = QtWidgets.QCheckBox("Headless")
        self.headless_cb.setChecked(False)
        row_opts.addWidget(self.headless_cb)
        
        row_opts.addWidget(QtWidgets.QLabel("Timeout (s):"))
        self.cap_timeout = QtWidgets.QSpinBox()
        self.cap_timeout.setRange(5, 120)
        self.cap_timeout.setValue(30)
        row_opts.addWidget(self.cap_timeout)
        
        self.btn_capture = QtWidgets.QPushButton("Open & Capture")
        self.btn_capture.clicked.connect(self._start_capture)
        row_opts.addWidget(self.btn_capture)
        L.addLayout(row_opts)
        
        # Captured items list
        L.addWidget(QtWidgets.QLabel("Captured Media:"))
        self.capture_list = QtWidgets.QListWidget()
        self.capture_list.setMinimumHeight(120)
        L.addWidget(self.capture_list)
        
        # Capture actions
        row_actions = QtWidgets.QHBoxLayout()
        self.btn_copy_selected = QtWidgets.QPushButton("Copy URL")
        self.btn_copy_selected.setEnabled(True)
        self.btn_copy_selected.clicked.connect(self._copy_selected_url)
        self.btn_copy_selected.setVisible(False)
        row_actions.addWidget(self.btn_copy_selected)
        
        self.btn_apply_headers = QtWidgets.QPushButton("Apply Headers")
        self.btn_apply_headers.setEnabled(True)
        self.btn_apply_headers.clicked.connect(self._apply_captured_headers)
        self.btn_apply_headers.setVisible(False)
        row_actions.addWidget(self.btn_apply_headers)
        
        self.btn_show_advanced = QtWidgets.QPushButton("Show Advanced")
        self.btn_show_advanced.clicked.connect(self._toggle_advanced_options)
        row_actions.addWidget(self.btn_show_advanced)
        L.addLayout(row_actions)
        
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
        res_layout.addWidget(self.btn_use_variant)
        
        L.addWidget(res_group)
        
        # Double-click captured item to copy URL
        try:
            self.capture_list.itemDoubleClicked.connect(lambda _: self._copy_selected_url())
        except Exception:
            pass
        
        self.tab_widget.addTab(capture_widget, "1. Capture")

    def _build_download_tab(self):
        """Build the download settings tab."""
        download_widget = QtWidgets.QWidget()
        L = QtWidgets.QVBoxLayout(download_widget)
        
        # Selected URL (read-only)
        row_url = QtWidgets.QHBoxLayout()
        row_url.addWidget(QtWidgets.QLabel("Selected URL:"))
        self.url_in = QtWidgets.QLineEdit()
        self.url_in.setPlaceholderText("Will be filled after capture and resolution selection")
        self.url_in.setReadOnly(True)
        row_url.addWidget(self.url_in, 1)
        L.addLayout(row_url)
        
        # Output file
        row_out = QtWidgets.QHBoxLayout()
        row_out.addWidget(QtWidgets.QLabel("Output file:"))
        self.out_in = QtWidgets.QLineEdit(str(Path.cwd() / "downloads" / "output.mp4"))
        row_out.addWidget(self.out_in, 1)
        btn_browse = QtWidgets.QPushButton("Browse…")
        btn_browse.clicked.connect(self._choose_output)
        row_out.addWidget(btn_browse)
        L.addLayout(row_out)
        
        # Advanced settings
        adv_group = QtWidgets.QGroupBox("Advanced Settings")
        grid = QtWidgets.QGridLayout(adv_group)
        
        grid.addWidget(QtWidgets.QLabel("User-Agent:"), 0, 0)
        self.ua_in = QtWidgets.QLineEdit()
        grid.addWidget(self.ua_in, 0, 1, 1, 2)
        
        grid.addWidget(QtWidgets.QLabel("Referer:"), 1, 0)
        self.ref_in = QtWidgets.QLineEdit()
        grid.addWidget(self.ref_in, 1, 1, 1, 2)
        
        grid.addWidget(QtWidgets.QLabel("Cookies:"), 2, 0)
        self.cookies_in = QtWidgets.QLineEdit()
        grid.addWidget(self.cookies_in, 2, 1, 1, 2)
        
        grid.addWidget(QtWidgets.QLabel("Concurrency:"), 3, 0)
        self.conc_in = QtWidgets.QLineEdit("4")
        grid.addWidget(self.conc_in, 3, 1)
        
        self.remux_cb = QtWidgets.QCheckBox("Remux to MP4 with ffmpeg")
        self.remux_cb.setChecked(True)
        grid.addWidget(self.remux_cb, 3, 2)
        
        L.addWidget(adv_group)
        
        # Download button
        self.btn_download_selected = QtWidgets.QPushButton("Download Selected Resolution")
        self.btn_download_selected.setEnabled(False)
        self.btn_download_selected.clicked.connect(self._download_selected)
        L.addWidget(self.btn_download_selected)
        
        # Alias for compatibility with existing code
        self.btn_start = self.btn_download_selected
        
        # Remember inputs
        self.remember_cb = QtWidgets.QCheckBox("Remember inputs")
        self.remember_cb.setChecked(True)
        L.addWidget(self.remember_cb)
        
        L.addStretch()  # Push everything to top
        
        self.tab_widget.addTab(download_widget, "2. Download")

    def _build_episodes_tab(self):
        """Build the episodes and batch download tab."""
        episodes_widget = QtWidgets.QWidget()
        L = QtWidgets.QVBoxLayout(episodes_widget)
        
        # Episode URL input
        url_group = QtWidgets.QGroupBox("TV Show/Movie URL")
        url_layout = QtWidgets.QVBoxLayout(url_group)
        
        row_url = QtWidgets.QHBoxLayout()
        row_url.addWidget(QtWidgets.QLabel("Content URL:"))
        self.episode_url_in = QtWidgets.QLineEdit()
        self.episode_url_in.setPlaceholderText("Enter TV show episode or movie URL (e.g., https://111movies.com/tv/123/1/1 or https://111movies.com/movie/123)")
        row_url.addWidget(self.episode_url_in, 1)
        url_layout.addLayout(row_url)
        
        # Detection button
        row_detect = QtWidgets.QHBoxLayout()
        self.btn_detect_episodes = QtWidgets.QPushButton("🔍 Detect Content")
        self.btn_detect_episodes.clicked.connect(self._detect_episodes)
        row_detect.addWidget(self.btn_detect_episodes)
        row_detect.addStretch()
        url_layout.addLayout(row_detect)
        
        L.addWidget(url_group)
        
        # Episode selection and range options
        selection_group = QtWidgets.QGroupBox("Content Selection")
        selection_layout = QtWidgets.QVBoxLayout(selection_group)
        
        # Detected episodes info
        self.episodes_info_label = QtWidgets.QLabel("No episodes detected yet")
        self.episodes_info_label.setStyleSheet("color: #666; font-style: italic;")
        selection_layout.addWidget(self.episodes_info_label)
        
        # Selection mode
        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(QtWidgets.QLabel("Selection Mode:"))
        
        self.selection_mode = QtWidgets.QButtonGroup()
        self.mode_single = QtWidgets.QRadioButton("Single Episode")
        self.mode_range = QtWidgets.QRadioButton("Episode Range")
        self.mode_all = QtWidgets.QRadioButton("All Episodes")
        self.mode_single.setChecked(True)
        
        self.selection_mode.addButton(self.mode_single, 0)
        self.selection_mode.addButton(self.mode_range, 1)
        self.selection_mode.addButton(self.mode_all, 2)
        
        mode_layout.addWidget(self.mode_single)
        mode_layout.addWidget(self.mode_range)
        mode_layout.addWidget(self.mode_all)
        mode_layout.addStretch()
        selection_layout.addLayout(mode_layout)
        
        # Single episode selection
        self.single_episode_widget = QtWidgets.QWidget()
        single_layout = QtWidgets.QHBoxLayout(self.single_episode_widget)
        single_layout.setContentsMargins(20, 0, 0, 0)
        single_layout.addWidget(QtWidgets.QLabel("Episode:"))
        self.episode_combo = QtWidgets.QComboBox()
        self.episode_combo.setEnabled(False)
        self.episode_combo.currentIndexChanged.connect(self._on_episode_selected)
        single_layout.addWidget(self.episode_combo, 1)
        single_layout.addStretch()
        selection_layout.addWidget(self.single_episode_widget)
        
        # Range selection
        self.range_widget = QtWidgets.QWidget()
        range_layout = QtWidgets.QVBoxLayout(self.range_widget)
        range_layout.setContentsMargins(20, 0, 0, 0)
        
        range_input_layout = QtWidgets.QHBoxLayout()
        range_input_layout.addWidget(QtWidgets.QLabel("From Episode:"))
        self.range_from = QtWidgets.QSpinBox()
        self.range_from.setMinimum(1)
        self.range_from.setEnabled(False)
        range_input_layout.addWidget(self.range_from)
        
        range_input_layout.addWidget(QtWidgets.QLabel("To Episode:"))
        self.range_to = QtWidgets.QSpinBox()
        self.range_to.setMinimum(1)
        self.range_to.setEnabled(False)
        range_input_layout.addWidget(self.range_to)
        range_input_layout.addStretch()
        range_layout.addLayout(range_input_layout)
        
        # Skip episodes
        skip_layout = QtWidgets.QHBoxLayout()
        skip_layout.addWidget(QtWidgets.QLabel("Skip Episodes:"))
        self.skip_episodes_in = QtWidgets.QLineEdit()
        self.skip_episodes_in.setPlaceholderText("e.g., 3,5,7 or 2-4,8")
        self.skip_episodes_in.setEnabled(False)
        skip_layout.addWidget(self.skip_episodes_in, 1)
        range_layout.addLayout(skip_layout)
        
        self.range_widget.setVisible(False)
        selection_layout.addWidget(self.range_widget)
        
        # Connect mode changes
        self.selection_mode.buttonClicked.connect(self._on_selection_mode_changed)
        
        L.addWidget(selection_group)
        
        # Download controls
        download_group = QtWidgets.QGroupBox("Download")
        download_layout = QtWidgets.QVBoxLayout(download_group)
        
        # Download button
        self.btn_download_episodes = QtWidgets.QPushButton("📥 Download Selected Episodes")
        self.btn_download_episodes.setEnabled(False)
        self.btn_download_episodes.clicked.connect(self._download_selected_episodes)
        download_layout.addWidget(self.btn_download_episodes)
        
        # Progress info
        self.batch_progress_label = QtWidgets.QLabel("")
        self.batch_progress_label.setStyleSheet("color: #666; font-size: 11px;")
        download_layout.addWidget(self.batch_progress_label)
        
        L.addWidget(download_group)
        
        L.addStretch()  # Push everything to top
        
        self.tab_widget.addTab(episodes_widget, "3. Episodes")

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
        """Open file dialog to select output file path."""
        f, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save As", str(self.out_in.text()))
        if f:
            self.out_in.setText(f)

    def _copy_selected_url(self):
        """Copy the selected captured URL to the main URL input field."""
        try:
            idx = self.capture_list.currentRow()
            if idx < 0 or idx >= len(self.captured_items):
                QtWidgets.QMessageBox.information(self, "Copy URL", "Select an item in the capture list first.")
                return
            url = self.captured_items[idx].get("url") or ""
            if not url:
                QtWidgets.QMessageBox.information(self, "Copy URL", "Selected item has no URL.")
                return
            QtWidgets.QApplication.clipboard().setText(url)
            self.status.setText("Copied URL to clipboard")
        except Exception:
            QtWidgets.QMessageBox.information(self, "Copy URL", "Could not copy the selected URL.")

    def _apply_captured_headers(self):
        """Apply headers from the selected captured request to input fields."""
        try:
            idx = self.capture_list.currentRow()
            if idx < 0 or idx >= len(self.captured_items):
                QtWidgets.QMessageBox.information(self, "Apply Headers", "Select an item in the capture list first.")
                return
            
            item = self.captured_items[idx]
            headers = item.get("headers", {})
            
            # Apply User-Agent
            ua = headers.get("User-Agent") or headers.get("user-agent")
            if ua:
                self.ua_in.setText(ua)
            
            # Apply Referer
            referer = headers.get("Referer") or headers.get("referer")
            if referer:
                self.ref_in.setText(referer)
            
            # Apply Authorization if present
            auth = headers.get("Authorization") or headers.get("authorization")
            if auth:
                current_cookies = self.cookies_in.text().strip()
                if "Authorization:" not in current_cookies:
                    if current_cookies and not current_cookies.endswith("; "):
                        current_cookies += "; "
                    current_cookies += f"Authorization: {auth}"
                    self.cookies_in.setText(current_cookies)
            
            # Apply any captured cookies
            cookie_header = item.get("cookie_header", "")
            if cookie_header and cookie_header != self.cookies_in.text().strip():
                self.cookies_in.setText(cookie_header)
            
            self.status.setText("Applied headers from selected request")
            
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Apply Headers", f"Could not apply headers: {e}")

    def _toggle_advanced_options(self):
        """Toggle visibility of advanced options like copy URL and apply headers buttons."""
        current_visible = self.btn_copy_selected.isVisible()
        new_visible = not current_visible
        
        self.btn_copy_selected.setVisible(new_visible)
        self.btn_apply_headers.setVisible(new_visible)
        self.btn_use_variant.setVisible(new_visible)
        
        if new_visible:
            self.btn_show_advanced.setText("Hide Advanced Options")
        else:
            self.btn_show_advanced.setText("Show Advanced Options")

    def _on_resolution_selected(self, index):
        """Handle resolution selection from the dropdown - automatically apply headers and prepare for download."""
        if index < 0 or not hasattr(self, 'variant_uris') or index >= len(self.variant_uris):
            return
            
        try:
            # Get the selected resolution URL
            selected_url = self.variant_uris[index]
            resolution_text = self.variant_combo.itemText(index)
            
            # Automatically apply the URL to the main input
            self.url_in.setText(selected_url)
            
            self._auto_generate_output_path()
            
            # Automatically apply captured headers if available
            self._auto_apply_headers_for_url(selected_url)
            
            # Update status
            self.status.setText(f"Selected resolution: {resolution_text}")
            self._append(f"✅ Auto-selected resolution: {resolution_text}")
            self._append(f"📋 URL applied: {selected_url}")
            
            # Enable download button
            self.btn_download_selected.setEnabled(True)
            
        except Exception as e:
            self._append(f"❌ Error selecting resolution: {e}")

    def _auto_apply_headers_for_url(self, url):
        """Automatically apply the best matching headers for the given URL."""
        try:
            if not hasattr(self, 'captured_items') or not self.captured_items:
                return
                
            # Find the best matching captured item for this URL
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
                
                # Apply User-Agent
                ua = headers.get("User-Agent") or headers.get("user-agent")
                if ua:
                    self.ua_in.setText(ua)
                
                # Apply Referer
                referer = headers.get("Referer") or headers.get("referer")
                if referer:
                    self.ref_in.setText(referer)
                
                # Apply cookies if available
                cookie_header = best_match.get("cookie_header", "")
                if cookie_header:
                    self.cookies_in.setText(cookie_header)
                
                self._append("🔧 Headers automatically applied")
                
        except Exception as e:
            self._append(f"⚠️ Could not auto-apply headers: {e}")

    def _auto_generate_output_path(self):
        """Auto-generate output file path based on page URL, or reset to default if page URL is empty."""
        try:
            page_url = self.page_in.text().strip()
            current_output = self.out_in.text().strip()
            
            if page_url:
                # Generate path based on page URL
                derived_path = self._derive_nested_output(page_url)
                self.out_in.setText(str(derived_path.resolve()))
                self._append(f"📁 Output auto-set: {derived_path}")
            else:
                # Reset to default when page URL is cleared
                default_path = str(Path.cwd() / "downloads" / "output.mp4")
                self.out_in.setText(default_path)
                self._append(f"📁 Output reset to default: {default_path}")
                
        except Exception as e:
            self._append(f"⚠️ Could not auto-generate output path: {e}")

    def _on_page_url_changed(self):
        """Handle page URL changes to auto-generate output file paths."""
        # Only auto-generate if we're not in the middle of loading settings
        if hasattr(self, '_loading_settings') and self._loading_settings:
            return
        self._auto_generate_output_path()

    def _derive_nested_output(self, url: str) -> Path:
        """Generate a nested output path based on the URL structure.
        
        Derives a nested output path mirroring the URL: domain/path/file.mp4.
        Examples:
          https://111movies.com/tv/48866/1/10 -> downloads/111movies.com/tv/48866/1/10.mp4
        
        Args:
            url: The URL to derive the output path from
            
        Returns:
            Path: The derived output file path
        """
        downloads_dir = Path.cwd() / "downloads"
        try:
            u = urllib.parse.urlparse(url)
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
            return downloads_dir / "output.mp4"

    def _detect_episodes(self):
        """Detect available episodes from the current page URL pattern."""
        try:
            # Use episode URL input if available, otherwise fall back to page URL
            episode_url = self.episode_url_in.text().strip()
            if not episode_url:
                episode_url = self.page_in.text().strip()
                if episode_url:
                    # Auto-fill episode URL from page URL
                    self.episode_url_in.setText(episode_url)
            
            if not episode_url:
                QtWidgets.QMessageBox.warning(self, "Missing URL", "Please enter a series/episode URL first.")
                return
            
            # Disable detect button during discovery
            self.btn_detect_episodes.setEnabled(False)
            self.btn_detect_episodes.setText("🔍 Discovering...")
            
            # Reset UI state
            self.episodes_info_label.setText("🔍 Discovering episodes...")
            self.episodes_info_label.setStyleSheet("color: #1976d2; font-style: italic;")
            
            # Start episode discovery in a separate thread
            self.episode_discovery_worker = EpisodeDiscoveryWorker(episode_url, self)
            self.episode_discovery_worker.episodes_found.connect(self._on_episodes_discovered)
            self.episode_discovery_worker.discovery_error.connect(self._on_episode_discovery_error)
            self.episode_discovery_worker.start()
            
        except Exception as e:
            self._append(f"❌ Error starting episode detection: {e}")
            self._reset_episode_detection_ui()

    def _on_episodes_discovered(self, episodes, original_url):
        """Handle discovered episodes from the worker thread."""
        try:
            if not episodes:
                self.episodes_info_label.setText("❌ No episodes found")
                self.episodes_info_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
                QtWidgets.QMessageBox.information(self, "No Episodes Found", "Could not detect episode pattern from the URL.")
                return
            
            # Store detected episodes
            self.detected_episodes = episodes
            
            # Update episodes info label
            self.episodes_info_label.setText(f"✅ Detected {len(episodes)} episodes (Episode {episodes[0][0]} to {episodes[-1][0]})")
            self.episodes_info_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            
            # Populate episode dropdown
            self.episode_combo.clear()
            self.episode_urls = []
            
            for episode_num, episode_url in episodes:
                self.episode_combo.addItem(f"Episode {episode_num}")
                self.episode_urls.append(episode_url)
            
            # Find and select current episode
            current_episode_index = -1
            for i, (_, url) in enumerate(episodes):
                if url == original_url:
                    current_episode_index = i
                    break
            
            if current_episode_index >= 0:
                self.episode_combo.setCurrentIndex(current_episode_index)
            
            # Enable controls
            self.episode_combo.setEnabled(True)
            
            # Set up range controls
            max_episode = len(episodes)
            self.range_from.setMaximum(max_episode)
            self.range_from.setValue(1)
            self.range_from.setEnabled(True)
            
            self.range_to.setMaximum(max_episode)
            self.range_to.setValue(max_episode)
            self.range_to.setEnabled(True)
            
            self.skip_episodes_in.setEnabled(True)
            
            # Update download button state
            self._update_episode_download_button_state()
            
            self._append(f"🎬 Detected {len(episodes)} episodes")
            if current_episode_index >= 0:
                self._append(f"📍 Current episode: {current_episode_index + 1}")
            
        except Exception as e:
            self._append(f"❌ Error processing discovered episodes: {e}")
        finally:
            self._reset_episode_detection_ui()

    def _on_episode_discovery_error(self, error_message):
        """Handle episode discovery errors."""
        self.episodes_info_label.setText("❌ Discovery failed")
        self.episodes_info_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
        self._append(f"❌ Episode discovery error: {error_message}")
        self._reset_episode_detection_ui()

    def _reset_episode_detection_ui(self):
        """Reset the episode detection UI to normal state."""
        self.btn_detect_episodes.setEnabled(True)
        self.btn_detect_episodes.setText("🔍 Detect Content")

    def _parse_episode_urls(self, base_url):
        """Parse episode URLs from a base URL pattern by actually checking episode availability.
        
        Supports patterns like:
        - https://111movies.com/tv/247043/1/1 (season/episode)
        - https://111movies.com/tv/247043/1 (episode only)
        - https://111movies.com/movie/247043 (movie)
        
        Returns:
            List of tuples: [(episode_number, episode_url), ...]
            For movies, returns: [(1, movie_url)]
        """
        try:
            u = urllib.parse.urlparse(base_url)
            path_parts = [p for p in u.path.split('/') if p]
            
            # Pattern: /movie/show_id (movie)
            if len(path_parts) >= 2 and path_parts[0] == 'movie':
                show_id = path_parts[1]
                movie_url = f"{u.scheme}://{u.netloc}/movie/{show_id}"
                
                # Check if movie exists
                if self._check_episode_exists(movie_url):
                    self._append(f"🎬 Found movie: {movie_url}")
                    return [(1, movie_url)]  # Return as single "episode"
                else:
                    self._append(f"❌ Movie not found: {movie_url}")
                    return []
            
            # Pattern: /tv/show_id/season/episode
            elif len(path_parts) >= 4 and path_parts[0] == 'tv':
                show_id = path_parts[1]
                season = path_parts[2]
                current_episode = int(path_parts[3])
                
                return self._discover_episodes_with_validation(u.scheme, u.netloc, show_id, season, current_episode, True)
            
            # Pattern: /tv/show_id/episode
            elif len(path_parts) >= 3 and path_parts[0] == 'tv':
                show_id = path_parts[1]
                current_episode = int(path_parts[2])
                
                return self._discover_episodes_with_validation(u.scheme, u.netloc, show_id, None, current_episode, False)
                
        except Exception as e:
            self._append(f"❌ Error parsing URL: {e}")
        
        return []

    def _discover_episodes_with_validation(self, scheme, netloc, show_id, season, current_episode, has_season):
        """Discover available episodes by actually checking if they exist."""
        episodes = []
        self._append("🔍 Discovering available episodes...")
        
        # Start from episode 1 and check availability
        max_check = 100  # Increased limit to handle more episodes
        consecutive_failures = 0
        max_consecutive_failures = 10  # Increased to handle larger gaps in episode numbering
        last_found_episode = 0
        total_failures = 0
        max_total_failures = 30  # Stop if we have too many total failures
        
        for ep in range(1, max_check + 1):
            if has_season:
                episode_url = f"{scheme}://{netloc}/tv/{show_id}/{season}/{ep}"
            else:
                episode_url = f"{scheme}://{netloc}/tv/{show_id}/{ep}"
            
            # Check if episode exists
            if self._check_episode_exists(episode_url):
                episodes.append((ep, episode_url))
                consecutive_failures = 0
                last_found_episode = ep
                self._append(f"✅ Found Episode {ep}")
            else:
                consecutive_failures += 1
                total_failures += 1
                self._append(f"❌ Episode {ep} not found")
                
                # Stop if we have too many total failures (likely no more episodes)
                if total_failures >= max_total_failures:
                    self._append(f"🛑 Stopping search after {total_failures} total failures")
                    break
                
                # Only stop due to consecutive failures if we're well past the last found episode
                # AND we haven't found any episodes recently
                if consecutive_failures >= max_consecutive_failures:
                    # If we haven't found any episodes yet, stop early
                    if last_found_episode == 0:
                        self._append(f"🛑 Stopping search - no episodes found in first {consecutive_failures} attempts")
                        break
                    # If we're far past the last found episode, stop
                    elif ep > (last_found_episode + max_consecutive_failures):
                        self._append(f"🛑 Stopping search after {consecutive_failures} consecutive failures beyond episode {last_found_episode}")
                        break
        
        if episodes:
            self._append(f"🎬 Discovery complete: Found {len(episodes)} episodes")
        else:
            self._append("❌ No episodes found")
            
        return episodes

    def _check_episode_exists(self, episode_url):
        """Check if an episode URL actually exists by making a HEAD request."""
        try:
            import urllib.request
            
            # Create request with proper headers
            req = urllib.request.Request(episode_url, method='HEAD')
            req.add_header('User-Agent', DEFAULT_UA)
            
            # Try to open the URL
            with urllib.request.urlopen(req, timeout=10) as response:
                # Consider 200-299 status codes as success
                return 200 <= response.getcode() < 300
                
        except Exception:
            # If any error occurs, assume episode doesn't exist
            return False

    def _on_episode_selected(self, index):
        """Handle episode selection from the dropdown."""
        if index < 0 or not hasattr(self, 'episode_urls') or index >= len(self.episode_urls):
            return
        
        try:
            selected_url = self.episode_urls[index]
            episode_num = index + 1
            
            # Update the page URL to the selected episode
            self.page_in.setText(selected_url)
            
            # Clear current capture data since we're switching episodes
            self.capture_list.clear()
            self.variant_combo.clear()
            self.variant_combo.setEnabled(False)
            self.btn_download_selected.setEnabled(False)
            self.url_in.clear()
            
            self._append(f"📺 Selected Episode {episode_num}: {selected_url}")
            self._append("🔄 Please capture this episode to get its video streams.")
            
        except Exception as e:
            self._append(f"❌ Error selecting episode: {e}")

    def _download_selected(self):
        """Download the currently selected resolution of the current episode."""
        if self.download_all_cb.isChecked():
            self._download_all_episodes()
        else:
            self._start()

    def _download_all_episodes(self):
        """Download all detected episodes."""
        if not hasattr(self, 'episode_urls') or not self.episode_urls:
            QtWidgets.QMessageBox.warning(self, "No Content", "Please detect content first.")
            return
        
        # Confirm with user
        reply = QtWidgets.QMessageBox.question(
            self, 
            "Download All Episodes", 
            f"This will download all {len(self.episode_urls)} episodes. This may take a while. Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        self._append(f"🚀 Starting batch download of {len(self.episode_urls)} episodes...")
        
        # Initialize batch download state
        self.batch_download_queue = self.episode_urls.copy()
        self.batch_download_current = 0
        self.batch_download_total = len(self.episode_urls)
        self.batch_download_failed = []
        
        # Start the batch download process
        self._process_next_episode()

    def _process_next_episode(self):
        """Process the next episode in the batch download queue."""
        if self.batch_download_current >= len(self.batch_download_queue):
            self._finish_batch_download()
            return
        
        episode_num, episode_url = self.batch_download_queue[self.batch_download_current]
        current_progress = self.batch_download_current + 1
        
        # Update progress display
        progress_text = f"📺 Episode {episode_num} ({current_progress}/{self.batch_download_total})"
        self.batch_progress_label.setText(progress_text)
        self.batch_progress_label.setStyleSheet("color: #1976d2; font-weight: bold;")
        
        # Update progress bar
        progress_percent = int((current_progress / self.batch_download_total) * 100)
        self.pbar.setValue(progress_percent)
        
        self._append(f"📺 Processing Episode {episode_num} ({current_progress}/{self.batch_download_total})")
        self._append(f"🔗 URL: {episode_url}")
        
        # Update the page URL to the current episode
        self.page_in.setText(episode_url)
        
        # Clear previous capture data
        self.capture_list.clear()
        self.variant_combo.clear()
        self.variant_combo.setEnabled(False)
        self.btn_download_selected.setEnabled(False)
        self.url_in.clear()
        self.captured_items = []
        self.captured_cookie = ""
        
        # Start capture for this episode
        self._start_batch_capture()

    def _start_batch_capture(self):
        """Start capturing media URLs for the current episode in batch mode."""
        page_url = self.page_in.text().strip()
        if not page_url:
            episode_num, _ = self.batch_download_queue[self.batch_download_current]
            self._append(f"❌ Error: No page URL for episode {episode_num}")
            self._skip_current_episode()
            return
        
        # Prepare headers
        headers = {}
        ua = self.ua_in.text().strip() or DEFAULT_UA
        ref = self.ref_in.text().strip() or page_url
        ck = self.cookies_in.text().strip()
        headers["User-Agent"] = ua
        headers["Referer"] = ref
        if ck:
            headers["Cookie"] = ck
        
        episode_num, _ = self.batch_download_queue[self.batch_download_current]
        self._append(f"🔍 Capturing streams for Episode {episode_num}...")
        
        # Update status
        self.status.setText(f"Capturing Episode {episode_num}...")
        
        # Run capture in a thread
        self.batch_cap_worker = CaptureWorker(page_url, headers, self.headless_cb.isChecked(), self.cap_timeout.value())
        self.batch_cap_worker.captured.connect(self._on_batch_captured)
        self.batch_cap_worker.error.connect(self._on_batch_capture_error)
        self.batch_cap_worker.start()

    @QtCore.pyqtSlot(list, str)
    def _on_batch_captured(self, items, cookie_header):
        """Handle captured media items for batch download."""
        episode_num = self.batch_download_current + 1
        
        if not items:
            self._append(f"❌ No streams found for Episode {episode_num}")
            self._skip_current_episode()
            return
        
        # Store captured data
        self.captured_items = items
        self.captured_cookie = cookie_header
        
        # Find the best quality stream (usually the first one after sorting)
        best_item = None
        for item in items:
            if item.get("url", "").endswith(".m3u8"):
                best_item = item
                break
        
        if not best_item:
            self._append(f"❌ No M3U8 streams found for Episode {episode_num}")
            self._skip_current_episode()
            return
        
        # Set the URL and start download
        self.url_in.setText(best_item["url"])
        
        # Auto-apply headers
        self._auto_apply_headers_for_url(best_item["url"])
        
        self._append(f"⬇️ Starting download for Episode {episode_num}...")
        
        # Start the download
        self._start_single_episode_download()

    def _on_batch_capture_error(self, error_msg):
        """Handle capture errors during batch download."""
        episode_num = self.batch_download_current + 1
        self._append(f"❌ Capture failed for Episode {episode_num}: {error_msg}")
        self._skip_current_episode()

    def _start_single_episode_download(self):
        """Start downloading the current episode in batch mode."""
        url = self.url_in.text().strip()
        if not url:
            self._append(f"❌ No download URL for Episode {self.batch_download_current + 1}")
            self._skip_current_episode()
            return
        
        # Generate output path for this episode
        try:
            page_url = self.page_in.text().strip()
            derived_path = self._derive_nested_output(page_url)
            out_path = str(derived_path)
        except Exception as e:
            self._append(f"❌ Could not generate output path for Episode {self.batch_download_current + 1}: {e}")
            self._skip_current_episode()
            return
        
        # Start the download worker
        self.batch_worker = HlsWorker(
            url=url,
            out_path=out_path,
            res_text="",  # Will be auto-detected
            bw=None,  # No bandwidth limit
            ua=self.ua_in.text().strip() or DEFAULT_UA,
            ref=self.ref_in.text().strip(),
            cookies=self.cookies_in.text().strip(),
            conc=4,  # Default concurrent downloads
            remux=self.remux_cb.isChecked()
        )
        
        self.batch_worker.log.connect(self._on_batch_progress)
        self.batch_worker.finished_ok.connect(self._on_batch_episode_complete)
        self.batch_worker.finished_err.connect(self._on_batch_episode_error)
        self.batch_worker.start()

    @QtCore.pyqtSlot(str)
    def _on_batch_progress(self, msg):
        """Handle progress updates during batch download."""
        # Just append the progress message
        self._append(msg)

    @QtCore.pyqtSlot(str)
    def _on_batch_episode_complete(self, success_msg):
        """Handle successful completion of an episode download."""
        episode_num = self.batch_download_current + 1
        self._append(f"✅ Episode {episode_num} downloaded successfully!")
        
        # Move to next episode
        self.batch_download_current += 1
        self._process_next_episode()

    @QtCore.pyqtSlot(str)
    def _on_batch_episode_error(self, error_msg):
        """Handle download errors during batch download."""
        episode_num = self.batch_download_current + 1
        self._append(f"❌ Episode {episode_num} download failed: {error_msg}")
        
        # Add to failed list
        self.batch_download_failed.append({
            'episode': episode_num,
            'url': self.batch_download_queue[self.batch_download_current],
            'error': error_msg
        })
        
        # Move to next episode
        self.batch_download_current += 1
        self._process_next_episode()

    def _skip_current_episode(self):
        """Skip the current episode and move to the next one."""
        episode_num = self.batch_download_current + 1
        self.batch_download_failed.append({
            'episode': episode_num,
            'url': self.batch_download_queue[self.batch_download_current],
            'error': 'Skipped due to capture/processing error'
        })
        
        self.batch_download_current += 1
        self._process_next_episode()

    def _finish_batch_download(self):
        """Finish the batch download process and show summary."""
        successful = self.batch_download_total - len(self.batch_download_failed)
        failed = len(self.batch_download_failed)
        
        self._append(f"🎉 Batch download completed!")
        self._append(f"📊 Summary: {successful} successful, {failed} failed out of {self.batch_download_total} episodes")
        
        if self.batch_download_failed:
            self._append("❌ Failed episodes:")
            for failure in self.batch_download_failed:
                self._append(f"   Episode {failure['episode']}: {failure['error']}")
        
        # Show completion dialog
        if failed == 0:
            QtWidgets.QMessageBox.information(
                self,
                "Batch Download Complete",
                f"All {successful} episodes downloaded successfully!"
            )
        else:
            QtWidgets.QMessageBox.warning(
                self,
                "Batch Download Complete",
                f"Download completed with {successful} successful and {failed} failed episodes.\n\nCheck the log for details about failed episodes."
            )
        
        # Clean up batch download state
        self.batch_download_queue = []
        self.batch_download_current = 0
        self.batch_download_total = 0
        self.batch_download_failed = []

    def _on_selection_mode_changed(self):
        """Handle selection mode changes in the Episodes tab."""
        mode = self.selection_mode.checkedId()
        
        # Show/hide appropriate widgets
        self.single_episode_widget.setVisible(mode == 0)  # Single
        self.range_widget.setVisible(mode == 1)  # Range
        
        # Update download button text
        if mode == 0:  # Single
            self.btn_download_episodes.setText("📥 Download Selected Episode")
        elif mode == 1:  # Range
            self.btn_download_episodes.setText("📥 Download Episode Range")
        else:  # All
            self.btn_download_episodes.setText("📥 Download All Episodes")
        
        # Update button state
        self._update_episode_download_button_state()

    def _update_episode_download_button_state(self):
        """Update the episode download button enabled state based on current selection."""
        has_episodes = hasattr(self, 'detected_episodes') and self.detected_episodes
        mode = self.selection_mode.checkedId()
        
        if not has_episodes:
            self.btn_download_episodes.setEnabled(False)
            return
        
        if mode == 0:  # Single
            self.btn_download_episodes.setEnabled(self.episode_combo.currentIndex() >= 0)
        elif mode == 1:  # Range
            self.btn_download_episodes.setEnabled(
                self.range_from.value() <= self.range_to.value() and 
                self.range_to.value() <= len(self.detected_episodes)
            )
        else:  # All
            self.btn_download_episodes.setEnabled(True)

    def _download_selected_episodes(self):
        """Download episodes based on current selection mode."""
        if not hasattr(self, 'detected_episodes') or not self.detected_episodes:
            QtWidgets.QMessageBox.warning(self, "No Content", "Please detect content first.")
            return
        
        mode = self.selection_mode.checkedId()
        episodes_to_download = []
        
        try:
            if mode == 0:  # Single episode
                index = self.episode_combo.currentIndex()
                if index >= 0:
                    episodes_to_download = [self.detected_episodes[index]]
            
            elif mode == 1:  # Range
                start = self.range_from.value() - 1  # Convert to 0-based index
                end = self.range_to.value()  # End is exclusive
                
                if start < 0 or end > len(self.detected_episodes) or start >= end:
                    QtWidgets.QMessageBox.warning(self, "Invalid Range", "Please enter a valid episode range.")
                    return
                
                episodes_to_download = self.detected_episodes[start:end]
                
                # Handle skip episodes
                skip_text = self.skip_episodes_in.text().strip()
                if skip_text:
                    skip_episodes = self._parse_skip_episodes(skip_text, start + 1, end)
                    episodes_to_download = [ep for i, ep in enumerate(episodes_to_download) 
                                          if (start + 1 + i) not in skip_episodes]
            
            else:  # All episodes
                episodes_to_download = self.detected_episodes[:]
            
            if not episodes_to_download:
                QtWidgets.QMessageBox.warning(self, "No Episodes", "No episodes selected for download.")
                return
            
            # Start batch download
            self._start_batch_download(episodes_to_download)
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to prepare episode download: {e}")

    def _parse_skip_episodes(self, skip_text, start_episode, end_episode):
        """Parse skip episodes string and return set of episode numbers to skip."""
        skip_episodes = set()
        
        for part in skip_text.split(','):
            part = part.strip()
            if not part:
                continue
                
            if '-' in part:
                # Range like "2-4"
                try:
                    range_start, range_end = map(int, part.split('-', 1))
                    for ep in range(range_start, range_end + 1):
                        if start_episode <= ep <= end_episode:
                            skip_episodes.add(ep)
                except ValueError:
                    continue
            else:
                # Single episode like "3"
                try:
                    ep = int(part)
                    if start_episode <= ep <= end_episode:
                        skip_episodes.add(ep)
                except ValueError:
                    continue
        
        return skip_episodes

    def _start_batch_download(self, episodes):
        """Start downloading a list of episodes."""
        self.batch_download_queue = episodes
        self.batch_download_current = 0
        self.batch_download_total = len(episodes)
        self.batch_download_failed = []
        
        self._append(f"🚀 Starting batch download of {self.batch_download_total} episodes...")
        self.batch_progress_label.setText(f"Preparing to download {self.batch_download_total} episodes...")
        
        # Disable the download button during batch download
        self.btn_download_episodes.setEnabled(False)
        
        # Start processing
        self._process_next_episode()

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
        self.cap_worker = CaptureWorker(page_url, headers, self.headless_cb.isChecked(), self.cap_timeout.value())
        self.cap_worker.captured.connect(self._on_captured)
        self.cap_worker.error.connect(self._on_capture_err)
        self.cap_worker.start()

    @QtCore.pyqtSlot(list, str)
    def _on_captured(self, items, cookie_header):
        """Handle captured media items and populate the capture list.
        
        Args:
            items: List of captured media items
            cookie_header: Cookie header value from the capture
        """
        self.status.setText("Captured")
        self.btn_capture.setEnabled(True)
        
        # Add timestamp to each captured item
        capture_time = time.time()
        for item in items:
            item["capture_timestamp"] = capture_time
            
        self.captured_items = items
        self.captured_cookie = cookie_header or ""
        if not self.cookies_in.text().strip() and self.captured_cookie:
            self.cookies_in.setText(self.captured_cookie)
        # Auto-fill Referer from captured request headers to avoid 403s
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
        # Populate list
        for it in items:
            ct = it.get("content_type") or ""
            self.capture_list.addItem(f"[{it['kind']}] {it['url']} {ct}")
        # Find master playlist; if body missing, fetch it synchronously as fallback
        master_body = None
        master_url = None
        
        # First, look for master playlist in captured bodies
        for it in items:
            u = it.get("url", "")
            b = it.get("body") or ""
            if b and "#EXT-X-STREAM-INF" in b:
                master_body = b
                master_url = u
                break
        
        # If no master playlist found, try to fetch from captured .m3u8 URLs
        if not master_body:
            # Try all .m3u8 URLs, not just the first one
            candidates = []
            for it in items:
                u = it.get("url", "").lower()
                if u.endswith(".m3u8"):
                    candidates.append(it.get("url"))
            
            # Try each candidate to find a master playlist
            for candidate in candidates:
                if candidate:
                    # Prefer Referer/Origin captured from the intercepted request
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
                        # reflect effective referer into the UI
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
                        # Compute Sec-Fetch-Site based on origin vs target
                        try:
                            cu = urllib.parse.urlparse(candidate)
                            on = urllib.parse.urlparse(origin).netloc if origin else None
                            site_val = "same-origin" if (on and cu.netloc == on) else "cross-site"
                        except Exception:
                            site_val = "cross-site"
                        hdrs.setdefault("Accept", "*/*")
                        hdrs.setdefault("Accept-Language", "en-US,en;q=0.9")
                        # Avoid brotli to keep urllib fallback simple
                        hdrs.setdefault("Accept-Encoding", "gzip, deflate")
                        hdrs.setdefault("Sec-Fetch-Dest", "empty")
                        hdrs.setdefault("Sec-Fetch-Mode", "cors")
                        hdrs.setdefault("Sec-Fetch-Site", site_val)
                        # Common client hints to satisfy stricter WAFs if not present
                        # Prefer values from captured headers if available
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
                        # Forward Authorization if present in captured headers
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
                            break  # Found a working master playlist, exit the loop
                    except Exception as e:
                        self._append(f"Failed to fetch master playlist from {candidate}: {e}")
                        continue  # Try the next candidate
        if master_body and master_url:
            variants = parse_master_playlist(master_body, master_url)
            if variants:
                self.variant_combo.setEnabled(True)
                self.btn_use_variant.setEnabled(True)
                self.btn_download_selected.setEnabled(False)  # Will be enabled when user selects
                self.variant_combo.clear()
                self.variant_uris = []
                
                # Sort variants by bandwidth (highest first) for better user experience
                sorted_variants = sorted(variants, key=lambda v: v.bandwidth or 0, reverse=True)
                
                for v in sorted_variants:
                    # Create more user-friendly labels
                    resolution = v.resolution or 'Unknown'
                    bandwidth = v.bandwidth
                    if bandwidth:
                        bandwidth_mbps = round(bandwidth / 1000000, 1)
                        label = f"{resolution} ({bandwidth_mbps} Mbps)"
                    else:
                        label = f"{resolution}"
                    
                    self.variant_combo.addItem(label)
                    self.variant_uris.append(v.uri)
                
                # Automatically select the highest quality (first item after sorting)
                if len(sorted_variants) > 0:
                    self.variant_combo.setCurrentIndex(0)
                    highest_res = sorted_variants[0].resolution or 'Unknown'
                    self._append(f"🎯 Found {len(sorted_variants)} resolutions. Highest quality ({highest_res}) auto-selected.")
                    self._append("📺 Select your preferred resolution from the dropdown above, then click 'Download Selected Resolution'.")
                else:
                    self._append("✅ Resolutions detected. Select one from the dropdown above.")
            else:
                self._append("No variants found in master playlist.")
        else:
            # Fallback: derive variants directly from captured .m3u8 URLs
            try:
                m3u8_urls = []
                for it in items:
                    u = (it.get("url") or "").lower()
                    if u.endswith(".m3u8"):
                        m3u8_urls.append(it.get("url"))
                # Try to infer resolution labels from URL path (supports base64-encoded segments like MTA4MA== → 1080)
                def infer_label(u: str) -> str:
                    try:
                        path_segs = [seg for seg in (urllib.parse.urlparse(u).path or "").split("/") if seg]
                        # Look for a segment that decodes from base64 to digits
                        for seg in path_segs:
                            try:
                                dec = base64.b64decode(seg + "==" if len(seg) % 4 != 0 else seg).decode("utf-8", errors="ignore")
                                dec2 = "".join(ch for ch in dec if ch.isdigit())
                                if dec2.isdigit():
                                    return dec2
                            except Exception:
                                pass
                        # Fallback: use any numeric-looking segment directly
                        for seg in path_segs:
                            if seg.isdigit():
                                return seg
                    except Exception:
                        pass
                    return "unknown"

                derived = [(infer_label(u), u) for u in m3u8_urls]
                # Prefer descending resolution if numeric
                def sort_key(t):
                    lbl = t[0]
                    return -(int(lbl) if lbl.isdigit() else -1)
                derived.sort(key=sort_key)

                if derived:
                    self.variant_combo.setEnabled(True)
                    self.btn_use_variant.setEnabled(True)
                    self.btn_download_selected.setEnabled(True)
                    self.variant_combo.clear()
                    self.variant_uris = []
                    for lbl, u in derived:
                        label = f"{lbl if lbl != 'unknown' else 'unknown'}"
                        self.variant_combo.addItem(label)
                        self.variant_uris.append(u)
                    self._append("Variants inferred from captured URLs. Select one and download.")
                else:
                    self._append("No master playlist found. Click play and try capture again.")
            except Exception:
                self._append("No master playlist found. Click play and try capture again.")

    @QtCore.pyqtSlot(str)
    def _on_capture_err(self, msg):
        """Handle capture operation errors.
        
        Args:
            msg: Error message from the capture operation
        """
        self.status.setText("Capture error")
        self._append(f"❌ Capture error: {msg}")
        self.btn_capture.setEnabled(True)

    def _use_selected_variant(self):
        """Use the selected variant from the capture list as the main URL."""
        idx = self.variant_combo.currentIndex()
        if idx < 0 or idx >= len(self.variant_uris):
            QtWidgets.QMessageBox.warning(self, "No selection", "Please select a resolution from the list.")
            return
        chosen_uri = self.variant_uris[idx]
        self.url_in.setText(chosen_uri)
        # Try to set Referer from captured request headers matching the chosen URI
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
        # auto-fill output file name based on page URL if using default/empty
        default_out = str(Path.cwd() / "downloads" / "output.mp4")
        cur_out = self.out_in.text().strip()
        if not cur_out or cur_out == default_out:
            try:
                # Use the original page URL for file path generation instead of variant URL
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
        """Download the selected variant from the capture list."""
        self._use_selected_variant()
        self._start()

    def _load_settings(self):
        """Load application settings from the configuration file."""
        self._loading_settings = True
        try:
            s = QtCore.QSettings(str(SETTINGS_PATH), QtCore.QSettings.IniFormat)
            self.url_in.setText(s.value("url", ""))
            self.out_in.setText(s.value("out", str(Path.cwd() / "downloads" / "output.mp4")))
            self.ua_in.setText(s.value("ua", DEFAULT_UA))
            self.ref_in.setText(s.value("ref", ""))
            self.cookies_in.setText(s.value("cookies", ""))
            # Force the new safer default concurrency shown in UI
            self.conc_in.setText("4")
            self.remux_cb.setChecked(bool(s.value("remux", True, type=bool)))
            self.page_in.setText(s.value("page", ""))
            self.headless_cb.setChecked(bool(s.value("headless", False, type=bool)))
            self.cap_timeout.setValue(int(s.value("cap_timeout", 30)))
            self.remember_cb.setChecked(bool(s.value("remember", True, type=bool)))
        finally:
            self._loading_settings = False

    def closeEvent(self, e):
        """Handle window close event and save settings.
        
        Args:
            e: The close event
        """
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
        """Append text to the log display.
        
        Args:
            s: Text to append to the log
        """
        self.log.append(s)
        self.log.ensureCursorVisible()

    @QtCore.pyqtSlot(int)
    def _on_percent(self, p: int):
        """Update the download progress bar.
        
        Args:
            p: Progress percentage (0-100)
        """
        self.pbar.setValue(p)
        self.status.setText(f"Downloading — {p}%")

    @QtCore.pyqtSlot(str)
    def _on_ok(self, path: str):
        """Handle successful download completion.
        
        Args:
            path: Path to the downloaded file
        """
        self._append(f"✅ Saved: {path}")
        self.status.setText("Completed")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.pbar.setValue(100)

    @QtCore.pyqtSlot(str)
    def _on_err(self, msg: str):
        """Handle download error.
        
        Args:
            msg: Error message
        """
        self._append(f"❌ Error: {msg}")
        self.status.setText("Error")
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)


def main():
    """Main entry point for the GUI application."""
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    # Allow Ctrl-C to exit cleanly while the Qt event loop runs
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