#!/usr/bin/env python3
"""
Build script to create small installer executables for all platforms.
This creates ~5-10MB installers instead of 800MB+ bundled apps.
"""

import os
import sys
import subprocess
import platform
import shutil
from pathlib import Path

class InstallerBuilder:
    def __init__(self):
        self.system = platform.system().lower()
        self.script_dir = Path(__file__).parent
        self.dist_dir = self.script_dir / "dist"
        
    def print_status(self, message, status="INFO"):
        """Print colored status messages"""
        colors = {
            "INFO": "\033[94m",
            "SUCCESS": "\033[92m", 
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "RESET": "\033[0m"
        }
        print(f"{colors.get(status, '')}{status}: {message}{colors['RESET']}")
    
    def check_dependencies(self):
        """Check if required tools are available"""
        self.print_status("Checking build dependencies...")
        
        # Check for PyInstaller
        try:
            import PyInstaller
            self.print_status("PyInstaller found ✓", "SUCCESS")
        except ImportError:
            self.print_status("Installing PyInstaller...", "WARNING")
            subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        
        # Check for UPX (optional, for compression)
        if shutil.which("upx"):
            self.print_status("UPX found - will compress executables ✓", "SUCCESS")
            self.use_upx = True
        else:
            self.print_status("UPX not found - executables will be larger", "WARNING")
            self.use_upx = False
    
    def build_python_installer(self):
        """Build the main Python installer into an executable"""
        self.print_status("Building Python installer executable...")
        
        # Create PyInstaller spec for the installer
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['install.py'],
    pathex=['{self.script_dir}'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HLS-Downloader-Installer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx={'True' if self.use_upx else 'False'},
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
'''
        
        spec_file = self.script_dir / "installer.spec"
        with open(spec_file, 'w') as f:
            f.write(spec_content)
        
        # Build with PyInstaller
        cmd = [sys.executable, "-m", "PyInstaller", "--clean", str(spec_file)]
        subprocess.run(cmd, cwd=self.script_dir, check=True)
        
        # Clean up
        spec_file.unlink()
        
        self.print_status("Python installer executable built ✓", "SUCCESS")
    
    def create_windows_installer(self):
        """Create Windows installer executable"""
        if self.system != "windows":
            self.print_status("Skipping Windows installer (not on Windows)", "WARNING")
            return
        
        self.print_status("Creating Windows installer...")
        
        # The batch file can be converted to exe using tools like Bat2Exe
        # For now, we'll provide the batch file
        batch_source = self.script_dir / "install.bat"
        batch_dest = self.dist_dir / "HLS-Downloader-Installer-Windows.bat"
        shutil.copy2(batch_source, batch_dest)
        
        self.print_status("Windows batch installer created ✓", "SUCCESS")
        self.print_status("Note: Use Bat2Exe or similar to convert to .exe", "INFO")
    
    def create_macos_installer(self):
        """Create macOS installer app"""
        if self.system != "darwin":
            self.print_status("Skipping macOS installer (not on macOS)", "WARNING")
            return
        
        self.print_status("Creating macOS installer app...")
        
        # Create app bundle structure
        app_name = "HLS Downloader Installer.app"
        app_dir = self.dist_dir / app_name
        contents_dir = app_dir / "Contents"
        macos_dir = contents_dir / "MacOS"
        resources_dir = contents_dir / "Resources"
        
        # Create directories
        macos_dir.mkdir(parents=True, exist_ok=True)
        resources_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy shell script as executable
        shell_source = self.script_dir / "install.sh"
        executable_dest = macos_dir / "HLS Downloader Installer"
        shutil.copy2(shell_source, executable_dest)
        os.chmod(executable_dest, 0o755)
        
        # Create Info.plist
        plist_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>HLS Downloader Installer</string>
    <key>CFBundleDisplayName</key>
    <string>HLS Downloader Installer</string>
    <key>CFBundleIdentifier</key>
    <string>com.hlsdownloader.installer</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleExecutable</key>
    <string>HLS Downloader Installer</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>'''
        
        plist_path = contents_dir / "Info.plist"
        with open(plist_path, 'w') as f:
            f.write(plist_content)
        
        self.print_status("macOS installer app created ✓", "SUCCESS")
    
    def create_linux_installer(self):
        """Create Linux installer"""
        self.print_status("Creating Linux installer...")
        
        # Copy shell script
        shell_source = self.script_dir / "install.sh"
        shell_dest = self.dist_dir / "HLS-Downloader-Installer-Linux.sh"
        shutil.copy2(shell_source, shell_dest)
        os.chmod(shell_dest, 0o755)
        
        self.print_status("Linux installer script created ✓", "SUCCESS")
    
    def create_readme(self):
        """Create README for installers"""
        readme_content = '''# HLS Downloader Smart Installers

These lightweight installers (~5-10MB) will download and set up HLS Downloader automatically.

## Why Smart Installers?

- **Tiny Size**: 5-10MB vs 800MB+ bundled apps
- **Always Updated**: Downloads latest version
- **Smart Setup**: Detects existing Python/browsers
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Installation Files

### Windows
- `HLS-Downloader-Installer-Windows.bat` - Batch installer
- `HLS-Downloader-Installer.exe` - Compiled executable (if available)

### macOS
- `HLS Downloader Installer.app` - Native app installer
- `HLS-Downloader-Installer-Linux.sh` - Shell script (also works on macOS)

### Linux
- `HLS-Downloader-Installer-Linux.sh` - Shell script installer

## Requirements

- **Python 3.8+** (installer will guide you if not available)
- **Internet connection** (for downloading)
- **~200MB disk space** (final installation)

## What the Installer Does

1. **Checks Python**: Verifies Python 3.8+ is available
2. **Downloads Repository**: Gets latest HLS Downloader code
3. **Sets Up Environment**: Creates virtual environment
4. **Installs Dependencies**: Downloads required packages
5. **Installs Browser**: Downloads Chromium for video processing
6. **Creates Launcher**: Adds shortcuts/launchers

## Installation Process

### Windows
1. Download `HLS-Downloader-Installer-Windows.bat`
2. Right-click and "Run as administrator" (if needed)
3. Follow the prompts

### macOS
1. Download `HLS Downloader Installer.app`
2. Double-click to run
3. Follow the prompts

### Linux
1. Download `HLS-Downloader-Installer-Linux.sh`
2. Make executable: `chmod +x HLS-Downloader-Installer-Linux.sh`
3. Run: `./HLS-Downloader-Installer-Linux.sh`

## Final Installation

After installation, you'll have:
- **Windows**: Desktop shortcut and Start Menu entry
- **macOS**: Application in Applications folder
- **Linux**: Application menu entry

## Troubleshooting

### Python Not Found
- **Windows**: Download from https://python.org/downloads
- **macOS**: `brew install python3` or download from python.org
- **Linux**: `sudo apt install python3 python3-pip` (Ubuntu/Debian)

### Permission Errors
- **Windows**: Run as administrator
- **macOS/Linux**: Ensure you have write permissions to installation directory

### Network Issues
- Check internet connection
- Try again later if GitHub is down
- Use VPN if GitHub is blocked

## Support

For issues, visit: https://github.com/M-Hammad-Faisal/HLS-Downloader/issues
'''
        
        readme_path = self.dist_dir / "README.md"
        with open(readme_path, 'w') as f:
            f.write(readme_content)
        
        self.print_status("README created ✓", "SUCCESS")
    
    def build_all(self):
        """Build all installers"""
        self.print_status("🚀 Building HLS Downloader Smart Installers...", "INFO")
        
        # Create dist directory
        self.dist_dir.mkdir(exist_ok=True)
        
        # Check dependencies
        self.check_dependencies()
        
        # Build Python installer executable
        self.build_python_installer()
        
        # Create platform-specific installers
        self.create_windows_installer()
        self.create_macos_installer()
        self.create_linux_installer()
        
        # Create documentation
        self.create_readme()
        
        # Show results
        self.print_status("🎉 All installers built successfully!", "SUCCESS")
        self.print_status(f"Installers available in: {self.dist_dir}", "INFO")
        
        # List created files
        print("\nCreated installers:")
        for file in self.dist_dir.iterdir():
            size = file.stat().st_size if file.is_file() else "N/A"
            if isinstance(size, int):
                if size > 1024*1024:
                    size_str = f"{size/(1024*1024):.1f}MB"
                elif size > 1024:
                    size_str = f"{size/1024:.1f}KB"
                else:
                    size_str = f"{size}B"
            else:
                size_str = "N/A"
            print(f"  - {file.name} ({size_str})")

if __name__ == "__main__":
    builder = InstallerBuilder()
    builder.build_all()