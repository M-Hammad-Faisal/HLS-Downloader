#!/usr/bin/env python3
"""
Build script to create smart installer scripts for all platforms.
This creates 3 simple installers that download, build, and install everything automatically.
"""

import os
import shutil
from pathlib import Path

class InstallerBuilder:
    def __init__(self):
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
    
    def create_windows_installer(self):
        """Copy Windows batch installer"""
        self.print_status("Creating Windows smart installer...")
        
        batch_source = self.script_dir / "install.bat"
        batch_dest = self.dist_dir / "HLS-Downloader-Smart-Installer-Windows.bat"
        shutil.copy2(batch_source, batch_dest)
        
        self.print_status("Windows smart installer created", "SUCCESS")
    
    def create_unix_installer(self):
        """Copy Unix shell installer (works for both macOS and Linux)"""
        self.print_status("Creating macOS/Linux smart installer...")
        
        shell_source = self.script_dir / "install.sh"
        shell_dest = self.dist_dir / "HLS-Downloader-Smart-Installer-Unix.sh"
        shutil.copy2(shell_source, shell_dest)
        os.chmod(shell_dest, 0o755)
        
        self.print_status("macOS/Linux smart installer created", "SUCCESS")
    
    def create_readme(self):
        """Create installation README"""
        self.print_status("Creating installation README...")
        
        readme_content = '''# HLS Downloader - Smart Installers

## 🚀 One-Click Installation

These smart installers download, build, and install HLS Downloader automatically.
**No pre-installed Python required!**

### 📦 Available Installers

#### Windows
- **File**: `HLS-Downloader-Smart-Installer-Windows.bat`
- **Size**: ~3KB
- **Requirements**: Windows 7+ with PowerShell
- **Installation**: Double-click the `.bat` file

#### macOS & Linux  
- **File**: `HLS-Downloader-Smart-Installer-Unix.sh`
- **Size**: ~12KB
- **Requirements**: macOS 10.12+ or Linux with bash
- **Installation**: 
  ```bash
  chmod +x HLS-Downloader-Smart-Installer-Unix.sh
  ./HLS-Downloader-Smart-Installer-Unix.sh
  ```

## 🔧 What Each Installer Does

1. **Downloads** portable Python (no system changes)
2. **Downloads** HLS Downloader source code
3. **Installs** all dependencies automatically
4. **Downloads** Playwright browsers
5. **Builds** the final application
6. **Creates** desktop shortcuts/app bundles
7. **Cleans up** temporary files
8. **Leaves** only the app and browsers

## 📍 Installation Locations

- **Windows**: `%USERPROFILE%\\HLS-Downloader\\`
- **macOS**: `~/Applications/HLS-Downloader/` + App Bundle
- **Linux**: `~/.local/share/HLS-Downloader/` + Desktop Entry

## 🎯 Final Result

- **Total Size**: ~200MB (vs 800MB+ bundled apps)
- **Includes**: Application + Chromium browser + All dependencies
- **No Setup**: Ready to use immediately after installation
- **Portable**: Self-contained, no system dependencies

## 🆘 Troubleshooting

If installation fails:
1. Check internet connection
2. Ensure you have write permissions to the installation directory
3. On Linux: Install `curl`, `wget`, and `unzip` if missing
4. On macOS: Install Xcode Command Line Tools if needed

## 📝 What's New in v2.1.3

- **Simplified**: Only 2 installer files (was 9+ files)
- **Smarter**: Automatic OS detection and setup
- **Faster**: Direct download and build process
- **Cleaner**: No leftover build artifacts
- **Better**: Improved error handling and user feedback

---

**Total download size**: ~50-80MB during installation
**Final app size**: ~200MB (includes everything needed)
**Installation time**: 2-5 minutes (depending on internet speed)
'''
        
        readme_path = self.dist_dir / "Installation-README.md"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        self.print_status("Installation README created", "SUCCESS")
    
    def build_all(self):
        """Build all smart installers"""
        self.print_status("Building HLS Downloader Smart Installers...", "INFO")
        
        # Create dist directory
        self.dist_dir.mkdir(exist_ok=True)
        
        # Clean existing files
        for file in self.dist_dir.glob("*"):
            if file.is_file():
                file.unlink()
        
        # Create smart installers
        self.create_windows_installer()
        self.create_unix_installer()
        self.create_readme()
        
        # Show results
        self.print_status("All smart installers built successfully!", "SUCCESS")
        self.print_status(f"Installers available in: {self.dist_dir}", "INFO")
        
        # List created files
        print("\nCreated smart installers:")
        for file in sorted(self.dist_dir.iterdir()):
            if file.is_file():
                size = file.stat().st_size
                if size > 1024:
                    size_str = f"{size/1024:.1f}KB"
                else:
                    size_str = f"{size}B"
                print(f"  - {file.name} ({size_str})")
        
        print("\n" + "="*50)
        print("🎉 SIMPLIFIED INSTALLER SYSTEM")
        print("="*50)
        print("✅ Reduced from 9+ files to just 2 installers")
        print("✅ Each installer does everything automatically")
        print("✅ No pre-installed Python required")
        print("✅ Downloads, builds, and installs in one step")
        print("✅ Creates proper app bundles/shortcuts")
        print("✅ Self-contained with all dependencies")
        print("="*50)

if __name__ == "__main__":
    builder = InstallerBuilder()
    builder.build_all()