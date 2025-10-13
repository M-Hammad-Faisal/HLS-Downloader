# HLS Video Downloader

A powerful Python application for downloading HLS (HTTP Live Streaming) video streams with a modern GUI interface.

## 🚀 Smart Installers Available!

**New lightweight installers (~5-10MB) that set up everything automatically!**

### Why Choose Smart Installers?
- 🎯 **Tiny Download**: 5-10MB vs 800MB+ bundled apps (98% smaller!)
- 🔄 **Always Updated**: Downloads the latest version automatically
- 🧠 **Smart Setup**: Detects existing Python/browsers on your system
- ⚡ **Fast Installation**: Sets up in minutes, not hours
- 🌍 **Cross-Platform**: Works on Windows, macOS, and Linux

### Download Smart Installer

Choose your platform from the [Latest Release](https://github.com/M-Hammad-Faisal/HLS-Downloader/releases/latest):

- **Windows**: `HLS-Downloader-Installer-Windows.exe` (~7MB)
- **macOS**: `HLS-Downloader-Installer-macOS.tar.gz` (~8MB)  
- **Linux**: `HLS-Downloader-Installer-Linux.sh` (~4KB)

**Requirements**: Internet connection, ~200MB disk space, Python 3.8+ (installer will guide you if missing)

## Features

- **Modern GUI Interface**: Clean and intuitive user interface built with Tkinter
- **HLS Stream Support**: Download video streams from HLS (.m3u8) URLs
- **Quality Selection**: Choose from available video qualities
- **Progress Tracking**: Real-time download progress with speed indicators
- **Batch Downloads**: Queue multiple downloads
- **Resume Support**: Resume interrupted downloads
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Installation Options

### Option 1: Smart Installer (Recommended) 🌟

**Tiny installers that set up everything automatically:**

1. Download the installer for your platform from [Releases](https://github.com/M-Hammad-Faisal/HLS-Downloader/releases/latest)
2. Run the installer (may need admin privileges)
3. Follow the prompts - it will handle everything!

The installer automatically:
- Checks for Python and guides installation if needed
- Downloads the latest HLS Downloader code
- Sets up a virtual environment
- Installs all dependencies
- Downloads Chromium browser
- Creates desktop shortcuts/launchers

### Option 2: Pre-built Bundles (Legacy)

Download the full bundled releases from the [Releases](https://github.com/M-Hammad-Faisal/HLS-Downloader/releases) page:

- **Windows**: `HLS-Downloader-v2.0.4-windows.zip` (475 MB)
- **macOS**: `HLS-Downloader-v2.0.4-macos.tar.gz` (800 MB)
- **Linux**: `HLS-Downloader-v2.0.4-linux.tar.gz` (578 MB)

All versions include bundled Playwright browsers - no additional setup required!

### Option 3: Manual Installation

#### Prerequisites
- Python 3.7+
- FFmpeg

#### Setup
```bash
pip install -r requirements.txt
playwright install chromium
```

### Development Setup
For development with linting tools:

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run linting with flake8
flake8 hlsdownloader/
```

## Usage

### GUI Application
```bash
python -m hlsdownloader.gui
```

### CLI Application

#### Direct Download
```bash
# Download HLS stream
python -m hlsdownloader.cli --url "https://example.com/playlist.m3u8"

# Specify resolution
python -m hlsdownloader.cli --url "https://example.com/playlist.m3u8" --res "1920x1080"

# Custom output path
python -m hlsdownloader.cli --url "https://example.com/playlist.m3u8" --out "video.mp4"
```

#### Interactive Mode (Web Capture)
```bash
# Interactive mode with page URL prompt
python -m hlsdownloader.cli --interactive

# Force interactive mode with specific page
python -m hlsdownloader.cli --url "https://example.com/video-page" --interactive
```

#### Advanced Options
```bash
# With authentication
python -m hlsdownloader.cli --url "URL" --cookies "session=abc123"

# Custom headers
python -m hlsdownloader.cli --url "URL" --ua "Custom-Agent" --ref "https://example.com"

# Keep original TS format
python -m hlsdownloader.cli --url "URL" --no-remux
```

### CLI Options
- `--url URL`: Source URL (media or .m3u8)
- `--interactive, -i`: Enable web capture mode
- `--out OUT`: Output file path
- `--mode {auto,http,hls}`: Download mode
- `--ua UA`: User-Agent header
- `--ref REF`: Referer header
- `--cookies COOKIES`: Cookie string
- `--res RES`: Preferred resolution (e.g., 1920x1080)
- `--bw BW`: Preferred bandwidth (bps)
- `--conc CONC`: Concurrent downloads (default: 4)
- `--no-remux`: Keep TS format instead of MP4
- `--no-headless`: Show browser for debugging

## How It Works

### HLS Download Process
1. Parse master .m3u8 playlist
2. Select best quality variant based on preferences
3. Download segments concurrently
4. Handle AES-128 decryption automatically
5. Concatenate segments and remux to MP4

### Web Capture Process
1. Launch Playwright browser
2. Intercept network requests
3. Detect media URLs
4. Present options for user selection
5. Download selected media

## Project Structure

```
HLS-Downloader/
├── .github/workflows/      # CI/CD automation
├── assets/                 # Application icons and images
├── downloads/              # Default output directory
├── hlsdownloader/          # Main package
│   ├── gui.py              # PyQt5 interface
│   ├── cli.py              # Command-line interface
│   ├── capture.py          # Web capture functionality
│   ├── hls.py              # HLS processing
│   ├── http_dl.py          # HTTP downloads
│   └── utils.py            # Utilities
├── main.py                 # Entry point
├── prepare_release.py      # Release automation
├── requirements.txt        # Dependencies
└── requirements-dev.txt    # Development dependencies
```

## Configuration

### GUI Settings
Settings are saved in `hls_gui_settings.ini`:
- Download directory
- User-Agent string
- Headers and cookies
- Concurrent download count

### Environment Variables
- `FFMPEG_PATH`: Custom FFmpeg path

## Supported Formats

**Input**: HLS streams (.m3u8), direct HTTP media, encrypted streams (AES-128)
**Output**: MP4 (default), TS (original format)

## Troubleshooting

**FFmpeg not found**: Install FFmpeg and add to PATH or set `FFMPEG_PATH`
**Browser issues**: Run `playwright install chromium`
**Decryption errors**: Install with `pip install pycryptodome`
**Network timeouts**: Check connection and geographic restrictions
**Permission errors**: Ensure write access to output directory
**GUI issues**: Verify PyQt5 installation

### macOS Security Warning
If you see "Apple could not verify 'HLS Downloader' is free of malware", follow these steps:

1. **Right-click method**: Right-click the app → "Open" → "Open" in the dialog
2. **System Settings method**: 
   - Go to System Settings → Privacy & Security
   - Scroll down to "Security" section
   - Click "Open Anyway" next to the blocked app message
3. **Terminal method**: Run `xattr -d com.apple.quarantine "/path/to/HLS Downloader.app"`

This warning appears because the app is not signed with an Apple Developer certificate. The app is safe to use.

### Debug Mode
Use `--no-headless` to see browser interactions and check console output for errors.

## Legal Notice

This tool is for downloading content you have legal rights to access. Users must comply with:
- Website terms of service
- Copyright laws
- Content licensing
- Local regulations

Do not use to bypass DRM, download copyrighted content without permission, or violate terms of service.

## Building Executables

### Assets Included
The project includes custom application icons:
- **Windows Icon**: `assets/icon.ico` - Used for Windows executable builds
- **macOS Icon**: `assets/icon.icns` - Used for macOS app bundle builds
- **Additional Assets**: `assets/HLS Downloader.png` - Project branding image

### Local Build
Build executable for your current platform:

```bash
# Install build dependencies
pip install -r requirements-dev.txt

# Build cross-platform release bundles
python prepare_release.py
```

**Build Output:**
- Built executables are placed in the `release_assets/` directory
- Icons are automatically embedded in the executables
- macOS builds create `.app` bundles with proper metadata

### Automated Builds (CI/CD)
The project includes GitHub Actions workflows for automated builds:

- **Triggers**: Push to main/master, tags, pull requests, manual dispatch
- **Platforms**: Windows (x64), macOS (x64, ARM64)
- **Features**: Custom icons, code signing ready, automatic releases
- **Artifacts**: Downloadable executables for each platform

#### Creating a Release
1. Tag your commit: `git tag v1.0.0`
2. Push the tag: `git push origin v1.0.0`
3. GitHub Actions automatically builds and creates a release with branded executables

#### Build Matrix
- **Windows**: `HLS-Downloader-windows-x64.exe` (with custom icon)
- **macOS Intel**: `HLS-Downloader-macos-x64.app` (with custom icon and bundle)
- **macOS Apple Silicon**: `HLS-Downloader-macos-arm64.app` (native ARM64 with custom icon)

### Build Features
- **Custom Branding**: Application icons embedded in all builds
- **Cross-Platform**: Supports Windows and macOS (Intel + Apple Silicon)
- **Bundle Creation**: macOS builds include proper app bundles
- **Dependency Bundling**: All required libraries included
- **Size Optimization**: UPX compression for smaller executables

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Submit a pull request

## License

Provided for educational and personal use. Ensure compliance with applicable laws and terms of service.