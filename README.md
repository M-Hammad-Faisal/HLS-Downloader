# VideoDownloader

A comprehensive Python application for downloading HLS (HTTP Live Streaming) video streams and media files. This tool provides both GUI and CLI interfaces for capturing and downloading video content from web pages.

## Features

### 🎥 HLS Stream Downloading
- Download HLS (.m3u8) streams with automatic quality selection
- Support for encrypted streams (AES-128) with automatic decryption
- Bandwidth and resolution-based stream selection
- Concurrent segment downloading for faster speeds
- Automatic remuxing to MP4 format

### 🌐 Web Capture
- Capture media URLs by intercepting network traffic from web pages
- Support for various media formats (HLS, MP4, etc.)
- Headless browser automation using Playwright
- Custom headers and authentication support

### 🖥️ User Interfaces
- **GUI**: Modern PyQt5-based graphical interface
- **CLI**: Command-line interface for automation and scripting
- Real-time progress tracking and logging
- Configurable download settings

### 🔧 Advanced Features
- Custom User-Agent and Referer headers
- Cookie support for authenticated sessions
- Configurable concurrent downloads
- Automatic output path generation
- Resume capability for interrupted downloads

## Installation

### Prerequisites
- Python 3.7 or higher
- FFmpeg (for video processing)

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Install Playwright Browsers
```bash
playwright install chromium
```

## Usage

### GUI Application
Launch the graphical interface:
```bash
python main.py
```

### CLI Downloader
Use the command-line interface:
```bash
python cli_downloader.py [URL] [OPTIONS]
```

#### CLI Options:
- `--output, -o`: Output file path
- `--resolution, -r`: Preferred resolution (e.g., "1920x1080")
- `--bandwidth, -b`: Maximum bandwidth preference
- `--user-agent, -ua`: Custom User-Agent header
- `--referer, -ref`: Custom Referer header
- `--cookies, -c`: Cookie string for authentication
- `--concurrent, -j`: Number of concurrent downloads (default: 4)
- `--no-remux`: Skip remuxing to MP4
- `--downloads-dir`: Downloads directory (default: ./downloads)

#### CLI Examples:
```bash
# Download with automatic quality selection
python cli_downloader.py "https://example.com/playlist.m3u8"

# Download with specific resolution
python cli_downloader.py "https://example.com/playlist.m3u8" -r "1920x1080"

# Download with custom output path
python cli_downloader.py "https://example.com/playlist.m3u8" -o "my_video.mp4"

# Download with authentication
python cli_downloader.py "https://example.com/playlist.m3u8" -c "session=abc123"
```

### Media Capture Tool
Capture media URLs from web pages:
```bash
python capture_m3u8.py [PAGE_URL] [OPTIONS]
```

#### Capture Options:
- `--timeout, -t`: Page load timeout in seconds (default: 20)
- `--user-agent, -ua`: Custom User-Agent header
- `--headless`: Run browser in headless mode (default: True)
- `--download, -d`: Automatically download captured streams
- `--output, -o`: Output directory for downloads

#### Capture Examples:
```bash
# Capture media URLs from a page
python capture_m3u8.py "https://example.com/video-page"

# Capture and automatically download
python capture_m3u8.py "https://example.com/video-page" --download

# Capture with custom timeout
python capture_m3u8.py "https://example.com/video-page" -t 30
```

## Project Structure

```
VideoDownloader/
├── main.py                 # GUI application launcher
├── cli_downloader.py       # CLI application launcher
├── capture_m3u8.py         # Media capture tool
├── requirements.txt        # Python dependencies
├── downloads/              # Default download directory
└── videodownloader/        # Main package
    ├── __init__.py         # Package initialization
    ├── gui.py              # PyQt5 GUI implementation
    ├── cli.py              # Command-line interface
    ├── capture.py          # Web page media capture
    ├── hls.py              # HLS stream processing
    ├── http_dl.py          # HTTP file downloading
    └── utils.py            # Utility functions
```

## Dependencies

### Core Dependencies
- **PyQt5** (≥5.15.0): GUI framework
- **aiohttp** (≥3.8.0): Async HTTP client for downloads
- **playwright** (≥1.40.0): Browser automation for media capture

### Optional Dependencies
- **pycryptodome** (≥3.15.0): AES decryption for encrypted HLS streams

## Configuration

### GUI Settings
The GUI application saves settings in `hls_gui_settings.ini` in the current working directory. Settings include:
- Default download directory
- User-Agent string
- Referer header
- Cookie values
- Concurrent download count

### Environment Variables
- `FFMPEG_PATH`: Custom path to FFmpeg executable (if not in PATH)

## Supported Formats

### Input Formats
- HLS streams (.m3u8 playlists)
- Direct HTTP media files
- Encrypted HLS streams (AES-128)

### Output Formats
- MP4 (default, remuxed from downloaded segments)
- TS (transport stream, original format)

## Legal Notice

This tool is intended for downloading content that you have the legal right to access and download. Users are responsible for ensuring they comply with:
- Website terms of service
- Copyright laws
- Content licensing agreements
- Local regulations

**Do not use this tool to:**
- Bypass DRM protection
- Download copyrighted content without permission
- Violate website terms of service
- Access content illegally

## Troubleshooting

### Common Issues

1. **FFmpeg not found**
   - Install FFmpeg and ensure it's in your PATH
   - Or set the `FFMPEG_PATH` environment variable

2. **Playwright browser not installed**
   - Run `playwright install chromium`

3. **AES decryption errors**
   - Install pycryptodome: `pip install pycryptodome`

4. **Network timeouts**
   - Increase timeout values in CLI options
   - Check your internet connection
   - Some streams may have geographic restrictions

5. **Permission errors**
   - Ensure write permissions to the output directory
   - Run with appropriate user permissions

### Debug Mode
Enable verbose logging by setting the environment variable:
```bash
export PYTHONPATH=.
python -m videodownloader.cli --verbose [URL]
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is provided as-is for educational and personal use. Please ensure you comply with all applicable laws and terms of service when using this tool.

## Version History

- **v0.1.0**: Initial release with HLS downloading and GUI
- Current version includes web capture, CLI interface, and enhanced features