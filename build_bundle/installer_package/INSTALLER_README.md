# HLS Video Downloader - Smart Installer

This installer automatically sets up the HLS Video Downloader application with all its dependencies, including browser automation components.

## What the Installer Does

The smart installer performs the following tasks automatically:

1. **System Compatibility Check**: Verifies Python 3.8+ and pip are available
2. **Virtual Environment**: Creates an isolated Python environment for the application
3. **Dependencies Installation**: Installs all required Python packages:
   - PyQt5 (GUI framework)
   - aiohttp (HTTP client)
   - playwright (browser automation)
   - pycryptodome (encryption support)
   - pyinstaller (for building executables)
4. **Browser Installation**: Downloads and installs Chromium browser for Playwright
5. **Application Setup**: Copies all application files to the installation directory
6. **Desktop Integration**: Creates desktop shortcuts and launcher scripts
7. **Uninstaller**: Provides an easy way to remove the application

## Installation Instructions

### Windows

1. **Download** the application files to a folder
2. **Double-click** `install.bat` or run it from Command Prompt
3. **Follow** the on-screen instructions
4. **Launch** the application from the desktop shortcut

### macOS

1. **Download** the application files to a folder
2. **Open Terminal** and navigate to the folder
3. **Run**: `./install.sh`
4. **Launch** the application from the desktop or Applications folder

### Linux

1. **Download** the application files to a folder
2. **Open Terminal** and navigate to the folder
3. **Run**: `./install.sh`
4. **Launch** the application from the desktop shortcut

## Installation Locations

The installer places files in the following locations:

### Windows
- **Application**: `%USERPROFILE%\AppData\Local\HLSVideoDownloader\`
- **Desktop Shortcut**: `%USERPROFILE%\Desktop\HLS Video Downloader.lnk`

### macOS
- **Application**: `~/Applications/HLSVideoDownloader/`
- **Desktop Shortcut**: `~/Desktop/HLS Video Downloader.app`

### Linux
- **Application**: `~/.local/share/HLSVideoDownloader/`
- **Desktop Shortcut**: `~/Desktop/HLS_Video_Downloader.desktop`

## Requirements

### Minimum System Requirements
- **Operating System**: Windows 10+, macOS 10.14+, or Linux (Ubuntu 18.04+)
- **Python**: Version 3.8 or higher
- **RAM**: 4 GB minimum, 8 GB recommended
- **Storage**: 2 GB free space (includes browser installation)
- **Internet**: Required for initial setup and browser installation

### Pre-Installation Requirements

#### Windows
- Python 3.8+ installed from [python.org](https://python.org)
- Make sure "Add Python to PATH" was checked during Python installation

#### macOS
- Python 3.8+ (install via Homebrew: `brew install python3` or from [python.org](https://python.org))
- Xcode Command Line Tools: `xcode-select --install`

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

#### Linux (CentOS/RHEL)
```bash
sudo yum install python3 python3-pip
```

## Features Included

After installation, you'll have access to:

- **GUI Application**: User-friendly interface for downloading videos
- **CLI Tool**: Command-line interface for advanced users and automation
- **Browser Automation**: Automatic handling of JavaScript-heavy sites
- **HLS Support**: Download HTTP Live Streaming (HLS) videos
- **HTTP Downloads**: Standard HTTP video file downloads
- **Resolution Selection**: Choose from available video qualities
- **Concurrent Downloads**: Multi-threaded downloading for faster speeds
- **Progress Tracking**: Real-time download progress and status

## Troubleshooting

### Common Issues

#### "Python is not installed or not in PATH"
- **Solution**: Install Python from [python.org](https://python.org) and ensure "Add Python to PATH" is checked

#### "Permission denied" on macOS/Linux
- **Solution**: Make sure the installer script is executable: `chmod +x install.sh`

#### "Failed to install Playwright browsers"
- **Solution**: Ensure you have a stable internet connection and sufficient disk space

#### Application won't start
- **Solution**: Try running the uninstaller and reinstalling, or check the installation logs

### Getting Help

If you encounter issues:

1. **Check the installation logs** displayed during setup
2. **Verify system requirements** are met
3. **Try running the installer as administrator** (Windows) or with `sudo` (Linux/macOS) if permission issues occur
4. **Ensure antivirus software** isn't blocking the installation

## Uninstallation

To remove the application:

### Windows
- Run `uninstall.bat` from the installation directory
- Or manually delete the installation folder

### macOS/Linux
- Run `./uninstall.sh` from the installation directory
- Or manually delete the installation folder

## Manual Installation (Advanced Users)

If you prefer to install manually:

1. **Clone or download** the source code
2. **Create virtual environment**: `python -m venv venv`
3. **Activate environment**: 
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`
4. **Install dependencies**: `pip install -r requirements.txt`
5. **Install browsers**: `python -m playwright install chromium`
6. **Run application**: `python main.py`

## Building Standalone Executable

After installation, you can build a standalone executable:

1. **Navigate** to the installation directory
2. **Activate** the virtual environment
3. **Run**: `python build_executable.py`

The executable will be created in the `dist` folder.

## Security Notes

- The installer creates an isolated virtual environment to avoid conflicts
- Browser automation uses Chromium in a sandboxed environment
- No personal data is collected or transmitted
- All downloads are performed locally on your machine

## License

This software is provided as-is. Please ensure you have the right to download any content you access with this tool.