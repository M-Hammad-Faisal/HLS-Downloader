#!/usr/bin/env python3
"""
HLS Downloader Smart Installer
A lightweight installer that downloads and sets up everything automatically.
Target size: ~5-10MB instead of 800MB+
"""

import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
import platform
import json
from pathlib import Path
import tempfile

class HLSDownloaderInstaller:
    def __init__(self):
        self.system = platform.system().lower()
        self.arch = platform.machine().lower()
        self.install_dir = self.get_install_directory()
        self.repo_url = "https://github.com/M-Hammad-Faisal/HLS-Downloader"
        self.python_required = "3.8"
        
    def get_install_directory(self):
        """Get the appropriate installation directory for each platform"""
        if self.system == "windows":
            return Path.home() / "AppData" / "Local" / "HLS Downloader"
        elif self.system == "darwin":  # macOS
            return Path.home() / "Applications" / "HLS Downloader"
        else:  # Linux
            return Path.home() / ".local" / "share" / "hls-downloader"
    
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
    
    def check_python(self):
        """Check if Python is available and meets requirements"""
        self.print_status("Checking Python installation...")
        
        try:
            # Check current Python version
            version = sys.version_info
            if version.major >= 3 and version.minor >= 8:
                self.print_status(f"Python {version.major}.{version.minor} found ✓", "SUCCESS")
                return sys.executable
        except:
            pass
        
        # Try to find Python in system
        python_commands = ["python3", "python", "py"]
        for cmd in python_commands:
            try:
                result = subprocess.run([cmd, "--version"], capture_output=True, text=True)
                if result.returncode == 0 and "Python 3." in result.stdout:
                    version_str = result.stdout.split()[1]
                    major, minor = map(int, version_str.split('.')[:2])
                    if major >= 3 and minor >= 8:
                        self.print_status(f"Python {version_str} found ✓", "SUCCESS")
                        return shutil.which(cmd)
            except:
                continue
        
        # Python not found or too old
        self.print_status("Python 3.8+ not found. Installing portable Python...", "WARNING")
        return self.install_portable_python()
    
    def install_portable_python(self):
        """Download and install portable Python"""
        self.print_status("Downloading portable Python...")
        
        # Python portable download URLs
        python_urls = {
            "windows": {
                "x86_64": "https://www.python.org/ftp/python/3.11.7/python-3.11.7-embed-amd64.zip",
                "x86": "https://www.python.org/ftp/python/3.11.7/python-3.11.7-embed-win32.zip"
            },
            "darwin": {
                # For macOS, we'll use pyenv or recommend system Python
                "arm64": None,
                "x86_64": None
            }
        }
        
        if self.system == "windows":
            arch_key = "x86_64" if "64" in self.arch else "x86"
            python_url = python_urls["windows"][arch_key]
            
            python_dir = self.install_dir / "python"
            python_dir.mkdir(parents=True, exist_ok=True)
            
            # Download Python
            python_zip = python_dir / "python.zip"
            self.download_file(python_url, python_zip)
            
            # Extract Python
            with zipfile.ZipFile(python_zip, 'r') as zip_ref:
                zip_ref.extractall(python_dir)
            
            python_zip.unlink()  # Remove zip file
            
            # Download get-pip.py
            pip_url = "https://bootstrap.pypa.io/get-pip.py"
            get_pip = python_dir / "get-pip.py"
            self.download_file(pip_url, get_pip)
            
            # Install pip
            python_exe = python_dir / "python.exe"
            subprocess.run([str(python_exe), str(get_pip)], check=True)
            
            self.print_status("Portable Python installed ✓", "SUCCESS")
            return str(python_exe)
        
        elif self.system == "darwin":
            # For macOS, guide user to install Python
            self.print_status("Please install Python 3.8+ from python.org or use Homebrew:", "ERROR")
            self.print_status("brew install python3", "INFO")
            sys.exit(1)
        
        else:  # Linux
            self.print_status("Please install Python 3.8+ using your package manager:", "ERROR")
            self.print_status("sudo apt install python3 python3-pip  # Ubuntu/Debian", "INFO")
            self.print_status("sudo yum install python3 python3-pip  # CentOS/RHEL", "INFO")
            sys.exit(1)
    
    def download_file(self, url, destination):
        """Download a file with progress"""
        self.print_status(f"Downloading {url.split('/')[-1]}...")
        
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, (block_num * block_size * 100) // total_size)
                print(f"\rProgress: {percent}%", end="", flush=True)
        
        urllib.request.urlretrieve(url, destination, progress_hook)
        print()  # New line after progress
    
    def check_browser(self):
        """Check for existing Chrome/Chromium installation"""
        self.print_status("Checking for existing browsers...")
        
        browser_paths = {
            "windows": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(os.getenv('USERNAME', ''))
            ],
            "darwin": [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"
            ],
            "linux": [
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/snap/bin/chromium"
            ]
        }
        
        for path in browser_paths.get(self.system, []):
            if os.path.exists(path):
                self.print_status(f"Found browser: {path} ✓", "SUCCESS")
                return path
        
        self.print_status("No system browser found. Will install Chromium...", "WARNING")
        return None
    
    def download_repo(self):
        """Download the HLS Downloader repository"""
        self.print_status("Downloading HLS Downloader...")
        
        # Create installation directory
        self.install_dir.mkdir(parents=True, exist_ok=True)
        
        # Download repository as ZIP
        repo_zip_url = f"{self.repo_url}/archive/refs/heads/master.zip"
        repo_zip = self.install_dir / "repo.zip"
        
        self.download_file(repo_zip_url, repo_zip)
        
        # Extract repository
        with zipfile.ZipFile(repo_zip, 'r') as zip_ref:
            zip_ref.extractall(self.install_dir)
        
        # Move contents from extracted folder to install dir
        extracted_folder = self.install_dir / "HLS-Downloader-master"
        if extracted_folder.exists():
            for item in extracted_folder.iterdir():
                dest_path = self.install_dir / item.name
                if dest_path.exists():
                    if dest_path.is_dir():
                        shutil.rmtree(dest_path)
                    else:
                        dest_path.unlink()
                shutil.move(str(item), str(dest_path))
            extracted_folder.rmdir()
        
        repo_zip.unlink()  # Remove zip file
        self.print_status("Repository downloaded ✓", "SUCCESS")
    
    def setup_environment(self, python_exe):
        """Set up Python virtual environment and install dependencies"""
        self.print_status("Setting up Python environment...")
        
        # Create virtual environment
        venv_dir = self.install_dir / "venv"
        subprocess.run([python_exe, "-m", "venv", str(venv_dir)], check=True)
        
        # Get venv Python executable
        if self.system == "windows":
            venv_python = venv_dir / "Scripts" / "python.exe"
            venv_pip = venv_dir / "Scripts" / "pip.exe"
        else:
            venv_python = venv_dir / "bin" / "python"
            venv_pip = venv_dir / "bin" / "pip"
        
        # Upgrade pip
        subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        
        # Install requirements
        requirements_file = self.install_dir / "requirements.txt"
        if requirements_file.exists():
            subprocess.run([str(venv_pip), "install", "-r", str(requirements_file)], check=True)
        
        # Install playwright and browsers
        subprocess.run([str(venv_pip), "install", "playwright"], check=True)
        subprocess.run([str(venv_python), "-m", "playwright", "install", "chromium"], check=True)
        
        self.print_status("Environment setup complete ✓", "SUCCESS")
        return str(venv_python)
    
    def create_launcher(self, python_exe):
        """Create launcher scripts/shortcuts"""
        self.print_status("Creating launcher...")
        
        if self.system == "windows":
            # Create batch file launcher
            launcher_content = f'''@echo off
cd /d "{self.install_dir}"
"{python_exe}" main.py %*
pause
'''
            launcher_path = self.install_dir / "HLS Downloader.bat"
            with open(launcher_path, 'w') as f:
                f.write(launcher_content)
            
            # Create desktop shortcut
            desktop = Path.home() / "Desktop"
            if desktop.exists():
                shortcut_path = desktop / "HLS Downloader.bat"
                shutil.copy2(launcher_path, shortcut_path)
        
        elif self.system == "darwin":
            # Create shell script launcher
            launcher_content = f'''#!/bin/bash
cd "{self.install_dir}"
"{python_exe}" main.py "$@"
'''
            launcher_path = self.install_dir / "launch.sh"
            with open(launcher_path, 'w') as f:
                f.write(launcher_content)
            os.chmod(launcher_path, 0o755)
            
            # Create app bundle
            self.create_macos_app(python_exe)
        
        else:  # Linux
            # Create shell script launcher
            launcher_content = f'''#!/bin/bash
cd "{self.install_dir}"
"{python_exe}" main.py "$@"
'''
            launcher_path = self.install_dir / "hls-downloader.sh"
            with open(launcher_path, 'w') as f:
                f.write(launcher_content)
            os.chmod(launcher_path, 0o755)
            
            # Create desktop entry
            self.create_linux_desktop_entry(launcher_path)
        
        self.print_status("Launcher created ✓", "SUCCESS")
    
    def create_macos_app(self, python_exe):
        """Create macOS app bundle"""
        app_dir = Path.home() / "Applications" / "HLS Downloader.app"
        contents_dir = app_dir / "Contents"
        macos_dir = contents_dir / "MacOS"
        resources_dir = contents_dir / "Resources"
        
        # Create directories
        macos_dir.mkdir(parents=True, exist_ok=True)
        resources_dir.mkdir(parents=True, exist_ok=True)
        
        # Create executable script
        executable_content = f'''#!/bin/bash
cd "{self.install_dir}"
"{python_exe}" main.py "$@"
'''
        executable_path = macos_dir / "HLS Downloader"
        with open(executable_path, 'w') as f:
            f.write(executable_content)
        os.chmod(executable_path, 0o755)
        
        # Create Info.plist
        plist_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>HLS Downloader</string>
    <key>CFBundleDisplayName</key>
    <string>HLS Downloader</string>
    <key>CFBundleIdentifier</key>
    <string>com.hlsdownloader.app</string>
    <key>CFBundleVersion</key>
    <string>2.0.4</string>
    <key>CFBundleExecutable</key>
    <string>HLS Downloader</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
</dict>
</plist>'''
        
        plist_path = contents_dir / "Info.plist"
        with open(plist_path, 'w') as f:
            f.write(plist_content)
        
        # Copy icon if available
        icon_source = self.install_dir / "assets" / "icon.icns"
        if icon_source.exists():
            shutil.copy2(icon_source, resources_dir / "icon.icns")
    
    def create_linux_desktop_entry(self, launcher_path):
        """Create Linux desktop entry"""
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        
        desktop_content = f'''[Desktop Entry]
Name=HLS Downloader
Comment=Download HLS video streams
Exec={launcher_path}
Icon={self.install_dir}/assets/icon.ico
Terminal=false
Type=Application
Categories=AudioVideo;Network;
'''
        
        desktop_file = desktop_dir / "hls-downloader.desktop"
        with open(desktop_file, 'w') as f:
            f.write(desktop_content)
        os.chmod(desktop_file, 0o755)
    
    def install(self):
        """Main installation process"""
        self.print_status("🚀 Starting HLS Downloader installation...", "INFO")
        self.print_status(f"Installing to: {self.install_dir}", "INFO")
        
        # Check if installation directory exists and ask for clean install
        if self.install_dir.exists():
            self.print_status("Existing installation found. Performing clean install...", "WARNING")
            shutil.rmtree(self.install_dir)
        
        try:
            # Step 1: Check/Install Python
            python_exe = self.check_python()
            
            # Step 2: Check browser
            self.check_browser()
            
            # Step 3: Download repository
            self.download_repo()
            
            # Step 4: Setup environment
            venv_python = self.setup_environment(python_exe)
            
            # Step 5: Create launcher
            self.create_launcher(venv_python)
            
            self.print_status("🎉 Installation completed successfully!", "SUCCESS")
            self.print_status(f"HLS Downloader is installed in: {self.install_dir}", "INFO")
            
            if self.system == "windows":
                self.print_status("You can run it from the desktop shortcut or start menu", "INFO")
            elif self.system == "darwin":
                self.print_status("You can run it from Applications folder", "INFO")
            else:
                self.print_status("You can run it from the applications menu", "INFO")
                
        except Exception as e:
            self.print_status(f"Installation failed: {str(e)}", "ERROR")
            sys.exit(1)

if __name__ == "__main__":
    installer = HLSDownloaderInstaller()
    installer.install()