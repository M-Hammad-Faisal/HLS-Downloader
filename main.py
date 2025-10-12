#!/usr/bin/env python3
"""Launcher for the HLS Downloader PyQt5 GUI application."""

from hlsdownloader.gui import main as run_gui


def main():
    """Launch the HLS Downloader PyQt5 GUI application."""
    run_gui()


if __name__ == "__main__":
    main()