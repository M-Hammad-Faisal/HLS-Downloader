#!/usr/bin/env python3
"""
HLS Video Downloader - Smart Installer
Automatically installs all dependencies, browsers, and creates shortcuts.
"""

import os
import sys
import platform
import subprocess
import shutil
import urllib.request
import zipfile
import tarfile
from pathlib import Path
import json
import tempfile

class VideoDownloaderInstaller:
    def __init__(self):
        self.system = platform.system().lower()
        self.machine = platform.machine().lower()
        self.install_dir = self.get_install_directory()
        self.app_name = "HLS Video Downloader"
        self.version = "1.0.0"
        
    def get_install_directory(self):
        """Get the appropriate installation directory for the platform."""
        if self.system == "windows":
            return Path.home() / "AppData" / "Local" / "HLSVideoDownloader"
        elif self.system == "darwin":  # macOS
            return Path.home() / "Applications" / "HLSVideoDownloader"
        else:  # Linux
            return Path.home() / ".local" / "share" / "HLSVideoDownloader"
    
    def log(self, message, level="INFO"):
        """Log installation progress."""
        print(f"[{level}] {message}")
    
    def check_python_version(self):
        """Check if Python version is compatible."""
        self.log("Checking Python version...")
        if sys.version_info < (3, 8):
            self.log("ERROR: Python 3.8 or higher is required!", "ERROR")
            return False
        self.log(f"Python {sys.version} - OK")
        return True
    
    def check_pip(self):
        """Check if pip is available."""
        self.log("Checking pip availability...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "--version"], 
                         check=True, capture_output=True)
            self.log("pip - OK")
            return True
        except subprocess.CalledProcessError:
            self.log("ERROR: pip is not available!", "ERROR")
            return False
    
    def create_virtual_environment(self):
        """Create a virtual environment for the application."""
        self.log("Creating virtual environment...")
        venv_path = self.install_dir / "venv"
        
        if venv_path.exists():
            self.log("Removing existing virtual environment...")
            shutil.rmtree(venv_path)
        
        try:
            subprocess.run([sys.executable, "-m", "venv", str(venv_path)], 
                         check=True, capture_output=True)
            self.log("Virtual environment created successfully")
            return venv_path
        except subprocess.CalledProcessError as e:
            self.log(f"ERROR: Failed to create virtual environment: {e}", "ERROR")
            return None
    
    def get_venv_python(self, venv_path):
        """Get the Python executable path in the virtual environment."""
        if self.system == "windows":
            return venv_path / "Scripts" / "python.exe"
        else:
            return venv_path / "bin" / "python"
    
    def get_venv_pip(self, venv_path):
        """Get the pip executable path in the virtual environment."""
        if self.system == "windows":
            return venv_path / "Scripts" / "pip.exe"
        else:
            return venv_path / "bin" / "pip"
    
    def install_dependencies(self, venv_path):
        """Install Python dependencies in the virtual environment."""
        self.log("Installing Python dependencies...")
        pip_exe = self.get_venv_pip(venv_path)
        
        dependencies = [
            "PyQt5>=5.15.0",
            "aiohttp>=3.8.0", 
            "playwright>=1.40.0",
            "pycryptodome>=3.15.0",
            "pyinstaller>=5.0.0"
        ]
        
        for dep in dependencies:
            self.log(f"Installing {dep}...")
            try:
                subprocess.run([str(pip_exe), "install", dep], 
                             check=True, capture_output=True)
                self.log(f"{dep} installed successfully")
            except subprocess.CalledProcessError as e:
                self.log(f"ERROR: Failed to install {dep}: {e}", "ERROR")
                return False
        
        return True
    
    def install_playwright_browsers(self, venv_path):
        """Install Playwright browsers."""
        self.log("Installing Playwright browsers...")
        python_exe = self.get_venv_python(venv_path)
        
        try:
            subprocess.run([str(python_exe), "-m", "playwright", "install", "chromium"], 
                         check=True, capture_output=True)
            self.log("Playwright browsers installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            self.log(f"ERROR: Failed to install Playwright browsers: {e}", "ERROR")
            return False
    
    def copy_application_files(self):
        """Copy application files to installation directory."""
        self.log("Copying application files...")
        
        # Create app directory
        app_dir = self.install_dir / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        
        # Files and directories to copy
        items_to_copy = [
            "hlsdownloader",
            "main.py",
            "requirements.txt",
            "assets",
            "build_executable.py",
            "HLS-Downloader.spec"
        ]
        
        current_dir = Path.cwd()
        
        for item in items_to_copy:
            src = current_dir / item
            if src.exists():
                dst = app_dir / item
                if src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                    self.log(f"Copied directory: {item}")
                else:
                    shutil.copy2(src, dst)
                    self.log(f"Copied file: {item}")
            else:
                self.log(f"WARNING: {item} not found, skipping", "WARNING")
        
        return True
    
    def create_launcher_script(self, venv_path):
        """Create launcher scripts for the application."""
        self.log("Creating launcher scripts...")
        
        python_exe = self.get_venv_python(venv_path)
        app_dir = self.install_dir / "app"
        
        if self.system == "windows":
            # Create Windows batch file
            launcher_path = self.install_dir / "HLS Video Downloader.bat"
            launcher_content = f'''@echo off
cd /d "{app_dir}"
"{python_exe}" main.py %*
pause
'''
        else:
            # Create Unix shell script
            launcher_path = self.install_dir / "hls-video-downloader"
            launcher_content = f'''#!/bin/bash
cd "{app_dir}"
"{python_exe}" main.py "$@"
'''
        
        with open(launcher_path, 'w') as f:
            f.write(launcher_content)
        
        if self.system != "windows":
            os.chmod(launcher_path, 0o755)
        
        self.log(f"Launcher script created: {launcher_path}")
        return launcher_path
    
    def create_desktop_shortcut(self, launcher_path):
        """Create desktop shortcut."""
        self.log("Creating desktop shortcut...")
        
        if self.system == "windows":
            self.create_windows_shortcut(launcher_path)
        elif self.system == "darwin":
            self.create_macos_app_bundle(launcher_path)
        else:
            self.create_linux_desktop_entry(launcher_path)
    
    def create_windows_shortcut(self, launcher_path):
        """Create Windows desktop shortcut."""
        try:
            import winshell
            from win32com.client import Dispatch
            
            desktop = winshell.desktop()
            shortcut_path = os.path.join(desktop, f"{self.app_name}.lnk")
            
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = str(launcher_path)
            shortcut.WorkingDirectory = str(self.install_dir / "app")
            shortcut.IconLocation = str(self.install_dir / "app" / "assets" / "icon.ico")
            shortcut.save()
            
            self.log(f"Desktop shortcut created: {shortcut_path}")
        except ImportError:
            self.log("WARNING: Could not create Windows shortcut (missing winshell/pywin32)", "WARNING")
    
    def create_macos_app_bundle(self, launcher_path):
        """Create macOS app bundle."""
        app_bundle = Path.home() / "Desktop" / f"{self.app_name}.app"
        contents_dir = app_bundle / "Contents"
        macos_dir = contents_dir / "MacOS"
        resources_dir = contents_dir / "Resources"
        
        # Create directory structure
        macos_dir.mkdir(parents=True, exist_ok=True)
        resources_dir.mkdir(parents=True, exist_ok=True)
        
        # Create Info.plist
        info_plist = contents_dir / "Info.plist"
        plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>com.hlsdownloader.app</string>
    <key>CFBundleName</key>
    <string>{self.app_name}</string>
    <key>CFBundleVersion</key>
    <string>{self.version}</string>
    <key>CFBundleIconFile</key>
    <string>icon.icns</string>
</dict>
</plist>'''
        
        with open(info_plist, 'w') as f:
            f.write(plist_content)
        
        # Create launcher executable
        launcher_exec = macos_dir / "launcher"
        with open(launcher_exec, 'w') as f:
            f.write(f'''#!/bin/bash
exec "{launcher_path}"
''')
        os.chmod(launcher_exec, 0o755)
        
        # Copy icon if available
        icon_src = self.install_dir / "app" / "assets" / "icon.icns"
        if icon_src.exists():
            shutil.copy2(icon_src, resources_dir / "icon.icns")
        
        self.log(f"macOS app bundle created: {app_bundle}")
    
    def create_linux_desktop_entry(self, launcher_path):
        """Create Linux desktop entry."""
        desktop_dir = Path.home() / "Desktop"
        desktop_entry = desktop_dir / f"{self.app_name.replace(' ', '_')}.desktop"
        
        icon_path = self.install_dir / "app" / "assets" / "HLS Downloader.png"
        
        entry_content = f'''[Desktop Entry]
Version=1.0
Type=Application
Name={self.app_name}
Comment=Download HLS and HTTP video streams
Exec={launcher_path}
Icon={icon_path if icon_path.exists() else "video-x-generic"}
Terminal=false
Categories=AudioVideo;Video;
'''
        
        with open(desktop_entry, 'w') as f:
            f.write(entry_content)
        
        os.chmod(desktop_entry, 0o755)
        self.log(f"Desktop entry created: {desktop_entry}")
    
    def create_uninstaller(self):
        """Create uninstaller script."""
        self.log("Creating uninstaller...")
        
        if self.system == "windows":
            uninstaller_path = self.install_dir / "uninstall.bat"
            uninstaller_content = f'''@echo off
echo Uninstalling {self.app_name}...
rmdir /s /q "{self.install_dir}"
echo Uninstallation complete.
pause
'''
        else:
            uninstaller_path = self.install_dir / "uninstall.sh"
            uninstaller_content = f'''#!/bin/bash
echo "Uninstalling {self.app_name}..."
rm -rf "{self.install_dir}"
echo "Uninstallation complete."
'''
        
        with open(uninstaller_path, 'w') as f:
            f.write(uninstaller_content)
        
        if self.system != "windows":
            os.chmod(uninstaller_path, 0o755)
        
        self.log(f"Uninstaller created: {uninstaller_path}")
    
    def install(self):
        """Main installation process."""
        self.log(f"Starting installation of {self.app_name} v{self.version}")
        self.log(f"Target platform: {self.system} ({self.machine})")
        self.log(f"Installation directory: {self.install_dir}")
        
        # Pre-installation checks
        if not self.check_python_version():
            return False
        
        if not self.check_pip():
            return False
        
        # Create installation directory
        self.install_dir.mkdir(parents=True, exist_ok=True)
        
        # Create virtual environment
        venv_path = self.create_virtual_environment()
        if not venv_path:
            return False
        
        # Install dependencies
        if not self.install_dependencies(venv_path):
            return False
        
        # Install Playwright browsers
        if not self.install_playwright_browsers(venv_path):
            return False
        
        # Copy application files
        if not self.copy_application_files():
            return False
        
        # Create launcher script
        launcher_path = self.create_launcher_script(venv_path)
        
        # Create desktop shortcut
        self.create_desktop_shortcut(launcher_path)
        
        # Create uninstaller
        self.create_uninstaller()
        
        self.log("=" * 60)
        self.log(f"✅ {self.app_name} installed successfully!")
        self.log(f"📁 Installation directory: {self.install_dir}")
        self.log(f"🚀 Launcher: {launcher_path}")
        self.log("🖥️  Desktop shortcut created")
        self.log("=" * 60)
        
        return True

def main():
    """Main entry point."""
    print("=" * 60)
    print("🎬 HLS Video Downloader - Smart Installer")
    print("=" * 60)
    
    installer = VideoDownloaderInstaller()
    
    try:
        success = installer.install()
        if success:
            print("\n🎉 Installation completed successfully!")
            print("You can now run the application from your desktop shortcut.")
        else:
            print("\n❌ Installation failed!")
            return 1
    except KeyboardInterrupt:
        print("\n\n⚠️  Installation cancelled by user.")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error during installation: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())