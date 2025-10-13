# HLS Video Downloader v1.0.0 Release Notes

## 🎉 What's New

### ✨ Features
- **Smart Cross-Platform Installer**: One-click installation on Windows, macOS, and Linux
- **Standalone Executables**: No Python installation required for end users
- **Desktop Integration**: Automatic shortcuts and app bundle creation
- **Clean Uninstallation**: Complete removal with dedicated uninstaller
- **Virtual Environment Isolation**: No system-wide dependency conflicts

### 🔧 Technical Improvements
- **PyInstaller Integration**: Optimized executable building
- **Dependency Management**: Automatic handling of PyQt5, aiohttp, playwright, and pycryptodome
- **Browser Automation**: Integrated Playwright browser installation
- **Cross-Platform Compatibility**: Tested on Windows 10/11, macOS 10.14+, Ubuntu 18.04+

## 📦 Download Options

### For End Users (Recommended)
- **Windows**: `HLS-Video-Downloader-1.0.0-windows-x64.zip`
- **macOS**: `HLS-Video-Downloader-1.0.0-darwin-universal.tar.gz`
- **Linux**: `HLS-Video-Downloader-1.0.0-linux-x64.tar.gz`

### Installation Methods
1. **One-Click**: Extract and run platform launcher (`install.bat` / `install.sh`)
2. **Smart Installer**: Run `python installer.py` for advanced options
3. **Standalone**: Use pre-built executables (no Python required)

## 🎯 System Requirements

### Minimum Requirements
- **OS**: Windows 7+ / macOS 10.14+ / Ubuntu 18.04+
- **RAM**: 512 MB available
- **Storage**: 200 MB free space
- **Network**: Internet connection for initial setup

### Recommended
- **OS**: Windows 10+ / macOS 11+ / Ubuntu 20.04+
- **RAM**: 2 GB available
- **Storage**: 500 MB free space
- **Network**: Broadband connection

## 🚀 Quick Start

### Windows
1. Download `HLS-Video-Downloader-1.0.0-windows-x64.zip`
2. Extract to a folder
3. Double-click `install.bat`
4. Launch from desktop shortcut

### macOS
1. Download `HLS-Video-Downloader-1.0.0-darwin-universal.tar.gz`
2. Extract the archive
3. Open Terminal in the folder
4. Run `./install.sh`
5. Launch from Applications

### Linux
1. Download `HLS-Video-Downloader-1.0.0-linux-x64.tar.gz`
2. Extract: `tar -xzf HLS-Video-Downloader-1.0.0-linux-x64.tar.gz`
3. Run: `cd HLS-Video-Downloader-1.0.0-linux-x64 && ./install.sh`
4. Launch from desktop

## 🛠️ For Developers

### Building from Source
```bash
git clone https://github.com/yourusername/VideoDownloader.git
cd VideoDownloader
python build_installer_bundle.py
```

### Development Setup
```bash
pip install -r requirements-dev.txt
python main.py
```

## 🐛 Known Issues

- **Windows Defender**: May flag executable as unknown (add exclusion)
- **macOS Gatekeeper**: First run requires "Open Anyway" in Security preferences
- **Linux Wayland**: Some Qt features may require X11 session

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/VideoDownloader/issues)
- **Documentation**: See included `INSTALLER_README.md`
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/VideoDownloader/discussions)

## 🙏 Acknowledgments

Built with:
- **PyQt5** - GUI framework
- **aiohttp** - HTTP client/server
- **Playwright** - Browser automation
- **PyInstaller** - Executable packaging
- **pycryptodome** - Cryptographic functions

---

**Full Changelog**: [v0.9.0...v1.0.0](https://github.com/yourusername/VideoDownloader/compare/v0.9.0...v1.0.0)
