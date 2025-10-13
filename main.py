#!/usr/bin/env python3
"""Launcher for the HLS Downloader PyQt5 GUI application."""

import os
import sys
import pathlib


def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller temp directory
        base = pathlib.Path(sys._MEIPASS)
    else:
        # Development mode
        base = pathlib.Path(__file__).parent
    return str(base / relative_path)


def setup_playwright_browsers():
    """Set up Playwright browser path for bundled browsers."""
    # Tell Playwright where the bundled browsers live
    browsers_path = resource_path("pw-browsers")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
    
    # Also set QT_QPA_PLATFORM for headless environments (helps with CI/CD)
    if not os.environ.get("DISPLAY") and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"


def main():
    """Launch the HLS Downloader PyQt5 GUI application."""
    # Set up Playwright browsers before any imports
    setup_playwright_browsers()
    
    # Import after setting up environment
    from hlsdownloader.gui import main as run_gui
    run_gui()


if __name__ == "__main__":
    main()