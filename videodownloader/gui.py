import sys
import tempfile
import asyncio
from pathlib import Path

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


class HlsWorker(QtCore.QThread):
    log = QtCore.pyqtSignal(str)
    percent = QtCore.pyqtSignal(int)
    finished_ok = QtCore.pyqtSignal(str)
    finished_err = QtCore.pyqtSignal(str)

    def __init__(self, url, out_path, res_text, bw, ua, ref, cookies, conc, remux):
        super().__init__()
        self.url = url
        self.out_path = Path(out_path)
        self.res_text = res_text
        self.bw = int(bw) if bw else None
        self.ua = ua or None
        self.ref = ref or None
        self.cookies = cookies or None
        self.conc = max(1, int(conc or 8))
        self.remux = bool(remux)
        self.cancel_flag = asyncio.Event()

    def cancel(self):
        self.log.emit("Cancel requested.")
        loop = getattr(self, "_loop", None)
        if loop:
            loop.call_soon_threadsafe(self.cancel_flag.set)
        else:
            self.cancel_flag.set()

    def run(self):
        try:
            asyncio.run(self._amain())
        except Exception as e:
            self.finished_err.emit(str(e))

    async def _amain(self):
        headers = {}
        if self.ua:
            headers["User-Agent"] = self.ua
        if self.ref:
            headers["Referer"] = self.ref
        if self.cookies:
            headers["Cookie"] = self.cookies

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


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HLS Downloader (Legal Streams Only)")
        self.resize(860, 560)
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        L = QtWidgets.QVBoxLayout(self)

        row_url = QtWidgets.QHBoxLayout()
        row_url.addWidget(QtWidgets.QLabel("HLS .m3u8 URL:"))
        self.url_in = QtWidgets.QLineEdit()
        self.url_in.setPlaceholderText("Paste a direct .m3u8 from a legal source (NOT a page URL / NOT blob:)")
        row_url.addWidget(self.url_in, 1)
        L.addLayout(row_url)

        row_out = QtWidgets.QHBoxLayout()
        row_out.addWidget(QtWidgets.QLabel("Output file:"))
        self.out_in = QtWidgets.QLineEdit(str(Path.cwd() / "output.mp4"))
        row_out.addWidget(self.out_in, 1)
        btn_browse = QtWidgets.QPushButton("Browse…")
        btn_browse.clicked.connect(self._choose_output)
        row_out.addWidget(btn_browse)
        L.addLayout(row_out)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("Prefer Resolution (e.g., 1920x1080):"), 0, 0)
        self.res_in = QtWidgets.QLineEdit()
        grid.addWidget(self.res_in, 0, 1)

        grid.addWidget(QtWidgets.QLabel("Prefer Bandwidth (bps):"), 0, 2)
        self.bw_in = QtWidgets.QLineEdit()
        grid.addWidget(self.bw_in, 0, 3)

        grid.addWidget(QtWidgets.QLabel("User-Agent:"), 1, 0)
        self.ua_in = QtWidgets.QLineEdit()
        grid.addWidget(self.ua_in, 1, 1)

        grid.addWidget(QtWidgets.QLabel("Referer:"), 1, 2)
        self.ref_in = QtWidgets.QLineEdit()
        grid.addWidget(self.ref_in, 1, 3)

        grid.addWidget(QtWidgets.QLabel("Cookies (header string):"), 2, 0)
        self.cookies_in = QtWidgets.QLineEdit()
        grid.addWidget(self.cookies_in, 2, 1, 1, 3)

        grid.addWidget(QtWidgets.QLabel("Concurrency:"), 3, 0)
        self.conc_in = QtWidgets.QLineEdit("8")
        grid.addWidget(self.conc_in, 3, 1)

        self.remux_cb = QtWidgets.QCheckBox("Remux to MP4 with ffmpeg (-c copy)")
        self.remux_cb.setChecked(True)
        grid.addWidget(self.remux_cb, 3, 2, 1, 2)

        L.addLayout(grid)

        row_btns = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton("Download")
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        row_btns.addWidget(self.btn_start)
        row_btns.addWidget(self.btn_cancel)
        L.addLayout(row_btns)

        self.pbar = QtWidgets.QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        L.addWidget(self.pbar)
        self.status = QtWidgets.QLabel("Status: idle")
        L.addWidget(self.status)
        self.log = QtWidgets.QTextEdit()
        self.log.setReadOnly(True)
        L.addWidget(self.log, 1)

        note = QtWidgets.QLabel(
            "Use only for NON-DRM streams you are authorized to save. "
            "Pages with <video src='blob:…'> do not expose a direct .m3u8 here."
        )
        note.setWordWrap(True)
        L.addWidget(note)

    def _choose_output(self):
        f, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save As", str(self.out_in.text()))
        if f:
            self.out_in.setText(f)

    def _start(self):
        url = self.url_in.text().strip()
        if not url:
            QtWidgets.QMessageBox.warning(self, "Missing URL", "Please paste a direct .m3u8 URL from a legal source.")
            return
        out_path = self.out_in.text().strip()
        if not out_path:
            QtWidgets.QMessageBox.warning(self, "Missing Output", "Please choose an output file path.")
            return

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.pbar.setValue(0)
        self.status.setText("Starting…")
        self.log.clear()
        self._append(f"Queued: {url}\nSaving to: {out_path}")

        self.worker = HlsWorker(
            url=url,
            out_path=out_path,
            res_text=self.res_in.text().strip(),
            bw=self.bw_in.text().strip(),
            ua=self.ua_in.text().strip(),
            ref=self.ref_in.text().strip(),
            cookies=self.cookies_in.text().strip(),
            conc=self.conc_in.text().strip(),
            remux=self.remux_cb.isChecked(),
        )
        self.worker.log.connect(self._append)
        self.worker.percent.connect(self._on_percent)
        self.worker.finished_ok.connect(self._on_ok)
        self.worker.finished_err.connect(self._on_err)
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()

    @QtCore.pyqtSlot(str)
    def _append(self, s: str):
        self.log.append(s)
        self.log.ensureCursorVisible()

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
    sys.exit(app.exec_())