#!/usr/bin/env python3
"""
Prepare HLS Video Downloader Release
Generates cross-platform installer bundles and release assets.
"""

import os
import sys
import platform
import subprocess
import shutil
import zipfile
import tarfile
import json
from pathlib import Path
from datetime import datetime

class ReleasePreparator:
    def __init__(self):
        self.version = "2.0.3"
        self.app_name = "HLS-Video-Downloader"
        self.current_dir = Path.cwd()
        self.release_dir = self.current_dir / "release_assets"
        self.current_platform = platform.system().lower()
        
        # Platform configurations
        self.platforms = {
            "windows": {
                "bundle_ext": ".zip",
                "executable_name": "HLS Downloader.exe",
                "launcher": "install.bat"
            },
            "darwin": {
                "bundle_ext": ".tar.gz", 
                "executable_name": "HLS Downloader.app",
                "launcher": "install.sh"
            },
            "linux": {
                "bundle_ext": ".tar.gz",
                "executable_name": "HLS Downloader", 
                "launcher": "install.sh"
            }
        }
    
    def log(self, message, level="INFO"):
        """Log with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def clean_release_dir(self):
        """Clean and create release directory."""
        if self.release_dir.exists():
            shutil.rmtree(self.release_dir)
        self.release_dir.mkdir(exist_ok=True)
        self.log("Release directory prepared")
    
    def create_platform_bundle(self, target_platform):
        """Create standalone executable bundle for specific platform."""
        self.log(f"Creating {target_platform} standalone executable bundle...")
        
        platform_config = self.platforms[target_platform]
        
        # Create platform-specific bundle directory
        bundle_name = f"{self.app_name}-{self.version}-{target_platform}"
        if target_platform == "darwin":
            bundle_name += "-universal"
        elif target_platform == "linux":
            bundle_name += "-x64"
        elif target_platform == "windows":
            bundle_name += "-x64"
        
        bundle_dir = self.release_dir / bundle_name
        bundle_dir.mkdir(exist_ok=True)
        
        # Build standalone executable with PyInstaller
        self.build_executable(target_platform)
        
        # Copy the built executable to bundle
        dist_base = self.current_dir / "dist"
        exe_name = platform_config["executable_name"]
        app_name = exe_name.replace(".exe", "").replace(".app", "")
        
        # Find the executable - PyInstaller creates a subdirectory
        possible_names = [
            app_name,  # Original name with spaces
            app_name.replace(" ", "_"),  # Spaces to underscores
            app_name.replace(" ", "-"),  # Spaces to hyphens
            app_name.replace(" ", ""),   # Remove spaces entirely
        ]
        
        exe_path = None
        for name in possible_names:
            candidate = dist_base / name / exe_name
            if candidate.exists():
                exe_path = candidate
                break
        
        if exe_path is None:
            # Try direct path as fallback
            direct_path = dist_base / exe_name
            if direct_path.exists():
                exe_path = direct_path
            else:
                available_dirs = [d.name for d in dist_base.iterdir() if d.is_dir()] if dist_base.exists() else []
                raise FileNotFoundError(f"Executable not found. Tried: {[str(dist_base / name / exe_name) for name in possible_names]}. Available dirs: {available_dirs}")
        
        if target_platform == "darwin" and exe_name.endswith(".app"):
            shutil.copytree(exe_path, bundle_dir / exe_name)
        else:
            shutil.copy2(exe_path, bundle_dir / exe_name)
        
        self.log(f"Included standalone executable: {exe_name}")
        
        # Copy only essential assets (no source code)
        assets_dir = self.current_dir / "assets"
        if assets_dir.exists():
            shutil.copytree(assets_dir, bundle_dir / "assets")
        
        # Create simple launcher scripts (no Python dependencies)
        self.create_launcher_scripts(bundle_dir, target_platform, exe_name)
        
        # Create installation instructions for standalone app
        self.create_standalone_instructions(bundle_dir, target_platform, exe_name)
        
        # Create archive
        archive_name = bundle_name + platform_config["bundle_ext"]
        archive_path = self.release_dir / archive_name
        
        if platform_config["bundle_ext"] == ".zip":
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(bundle_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(bundle_dir)
                        zipf.write(file_path, arcname)
        else:
            with tarfile.open(archive_path, 'w:gz') as tarf:
                tarf.add(bundle_dir, arcname=bundle_name)
        
        # Clean up bundle directory
        shutil.rmtree(bundle_dir)
        
        size_mb = archive_path.stat().st_size / 1024 / 1024
        self.log(f"Created {target_platform} bundle: {archive_name} ({size_mb:.1f} MB)")
        
        return archive_path
    
    def install_playwright_browsers(self):
        """Install Playwright browsers to local pw-browsers directory."""
        self.log("Installing Playwright browsers for bundling...")
        
        browsers_dir = self.current_dir / "pw-browsers"
        
        # Remove existing browsers directory if it exists
        if browsers_dir.exists():
            shutil.rmtree(browsers_dir)
        
        # Set environment variable to install browsers in local directory
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
        
        try:
            # Install only Chromium to keep bundle size reasonable (~280MB vs ~650MB for all browsers)
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            subprocess.run(cmd, check=True, env=env, cwd=self.current_dir)
            self.log(f"Successfully installed Playwright browsers to {browsers_dir}")
            
            # Verify installation
            if not browsers_dir.exists():
                raise RuntimeError("Playwright browsers directory was not created")
                
            # Log browser directory size for reference
            total_size = sum(f.stat().st_size for f in browsers_dir.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            self.log(f"Playwright browsers directory size: {size_mb:.1f} MB")
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to install Playwright browsers: {e}")

    def build_executable(self, target_platform):
        """Build standalone executable using PyInstaller."""
        self.log(f"Building standalone executable for {target_platform}...")
        
        # Install Playwright browsers first
        self.install_playwright_browsers()
        
        platform_config = self.platforms[target_platform]
        
        # Clean previous builds
        dist_dir = self.current_dir / "dist"
        build_dir = self.current_dir / "build"
        if dist_dir.exists():
            shutil.rmtree(dist_dir)
        if build_dir.exists():
            shutil.rmtree(build_dir)
        
        # Determine path separator for --add-data (OS-specific)
        path_sep = ";" if target_platform == "windows" else ":"
        
        # PyInstaller command
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onedir",  # Create a one-folder bundle
            "--windowed" if target_platform in ["windows", "darwin"] else "--console",
            "--name", platform_config["executable_name"].replace(".exe", "").replace(".app", ""),
            "--add-data", f"{self.current_dir / 'assets'}{path_sep}assets",
            # Note: We'll copy pw-browsers manually after PyInstaller to avoid binary processing issues
            "--hidden-import", "hlsdownloader",
            "--hidden-import", "hlsdownloader.gui",
            "--hidden-import", "hlsdownloader.cli",
            "--hidden-import", "hlsdownloader.hls",
            "--hidden-import", "hlsdownloader.capture",
            "--hidden-import", "hlsdownloader.http_dl",
            "--hidden-import", "hlsdownloader.utils",
            "--hidden-import", "playwright._impl._driver",
            "--hidden-import", "playwright._impl._transport",
            "--hidden-import", "playwright._impl._connection",
            "--clean",
            str(self.current_dir / "main.py")
        ]
        
        # Add icon if available
        if target_platform == "windows":
            icon_path = self.current_dir / "assets" / "icon.ico"
        elif target_platform == "darwin":
            icon_path = self.current_dir / "assets" / "icon.icns"
        else:  # linux
            icon_path = None
            
        if icon_path and icon_path.exists():
            cmd.extend(["--icon", str(icon_path)])
        
        # Add platform-specific options
        if target_platform == "darwin":
            cmd.extend(["--osx-bundle-identifier", "com.hlsdownloader.app"])
        
        try:
            subprocess.run(cmd, check=True, cwd=self.current_dir)
            self.log(f"Successfully built executable for {target_platform}")
            
            # Manually copy pw-browsers directory to avoid PyInstaller binary processing issues
            self.copy_browsers_to_dist(target_platform)
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to build executable: {e}")
    
    def copy_browsers_to_dist(self, target_platform):
        """Manually copy pw-browsers directory to the distribution folder."""
        self.log("Copying Playwright browsers to distribution folder...")
        
        platform_config = self.platforms[target_platform]
        app_name = platform_config["executable_name"].replace(".exe", "").replace(".app", "")
        
        # Find the distribution directory - try multiple possible names
        dist_base = self.current_dir / "dist"
        possible_names = [
            app_name,  # Original name with spaces
            app_name.replace(" ", "_"),  # Spaces to underscores
            app_name.replace(" ", "-"),  # Spaces to hyphens
            app_name.replace(" ", ""),   # Remove spaces entirely
        ]
        
        dist_dir = None
        for name in possible_names:
            candidate = dist_base / name
            if candidate.exists() and candidate.is_dir():
                dist_dir = candidate
                break
        
        if dist_dir is None:
            # List available directories for debugging
            available_dirs = [d.name for d in dist_base.iterdir() if d.is_dir()] if dist_base.exists() else []
            raise RuntimeError(f"Distribution directory not found. Tried: {possible_names}. Available: {available_dirs}")
        
        self.log(f"Found distribution directory: {dist_dir}")
        
        # Copy pw-browsers directory
        src_browsers = self.current_dir / "pw-browsers"
        dst_browsers = dist_dir / "pw-browsers"
        
        if src_browsers.exists():
            if dst_browsers.exists():
                shutil.rmtree(dst_browsers)
            shutil.copytree(src_browsers, dst_browsers)
            self.log(f"Successfully copied Playwright browsers to {dst_browsers}")
        else:
            self.log("Warning: pw-browsers directory not found, skipping browser copy")
    
    def create_launcher_scripts(self, bundle_dir, platform, exe_name):
        """Create simple launcher scripts for standalone executables."""
        
        if platform == "windows":
            launcher_content = f'''@echo off
echo Starting HLS Downloader...
start "" "{exe_name}"
'''
            with open(bundle_dir / "Launch_HLS_Downloader.bat", "w") as f:
                f.write(launcher_content)
                
        elif platform in ["darwin", "linux"]:
            launcher_content = f'''#!/bin/bash
echo "Starting HLS Downloader..."
cd "$(dirname "$0")"
./{exe_name}
'''
            launcher_path = bundle_dir / "Launch_HLS_Downloader.sh"
            with open(launcher_path, "w") as f:
                f.write(launcher_content)
            os.chmod(launcher_path, 0o755)
    
    def create_standalone_instructions(self, bundle_dir, platform, exe_name):
        """Create installation instructions for standalone executables."""
        
        if platform == "windows":
            instructions = f"""# Windows Installation Instructions

## Quick Start
1. Extract this ZIP file to any folder
2. Double-click `{exe_name}` to run HLS Downloader
3. Or use `Launch_HLS_Downloader.bat` for easier access

## Features
- **No Python Required**: Standalone executable
- **No Installation Needed**: Just extract and run
- **Portable**: Can be run from any folder or USB drive

## System Requirements
- Windows 7 or later
- 100 MB free disk space
- Internet connection (for downloading videos)

## Troubleshooting
- If Windows blocks the app, click "More info" → "Run anyway"
- Allow app in Windows Defender if prompted
- Run as Administrator if you encounter permission issues
"""
        elif platform == "darwin":
            instructions = f"""# macOS Installation Instructions

## Quick Start
1. Extract this archive to Applications folder (or any location)
2. Double-click `{exe_name}` to run HLS Downloader
3. Or use `Launch_HLS_Downloader.sh` from Terminal

## Features
- **No Python Required**: Standalone app bundle
- **No Installation Needed**: Just extract and run
- **Native macOS App**: Integrates with macOS properly

## System Requirements
- macOS 10.14 (Mojave) or later
- 100 MB free disk space
- Internet connection (for downloading videos)

## Troubleshooting
- If macOS blocks the app: System Preferences → Security & Privacy → "Open Anyway"
- Grant permissions when prompted (Downloads folder access, etc.)
- For Terminal use: `chmod +x Launch_HLS_Downloader.sh`
"""
        else:  # linux
            instructions = f"""# Linux Installation Instructions

## Quick Start
1. Extract this archive to any folder
2. Run: `./{exe_name}` from terminal
3. Or use `Launch_HLS_Downloader.sh` for easier access

## Features
- **No Python Required**: Standalone executable
- **No Installation Needed**: Just extract and run
- **Portable**: Can be run from any folder

## System Requirements
- Ubuntu 18.04+ / Debian 10+ / CentOS 7+ / Fedora 30+
- 100 MB free disk space
- Internet connection (for downloading videos)

## Troubleshooting
- Make executable: `chmod +x {exe_name}`
- Install missing libraries if needed: `sudo apt install libxcb1`
- For GUI issues, install: `sudo apt install libqt5gui5`
"""
        
        with open(bundle_dir / f"README_{platform.upper()}.md", 'w') as f:
            f.write(instructions)
    

    
    def create_release_notes(self):
        """Create comprehensive release notes."""
        release_notes = f"""# HLS Video Downloader v{self.version} Release Notes

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
- **Windows**: `{self.app_name}-{self.version}-windows-x64.zip`
- **macOS**: `{self.app_name}-{self.version}-darwin-universal.tar.gz`
- **Linux**: `{self.app_name}-{self.version}-linux-x64.tar.gz`

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
1. Download `{self.app_name}-{self.version}-windows-x64.zip`
2. Extract to a folder
3. Double-click `install.bat`
4. Launch from desktop shortcut

### macOS
1. Download `{self.app_name}-{self.version}-darwin-universal.tar.gz`
2. Extract the archive
3. Open Terminal in the folder
4. Run `./install.sh`
5. Launch from Applications

### Linux
1. Download `{self.app_name}-{self.version}-linux-x64.tar.gz`
2. Extract: `tar -xzf {self.app_name}-{self.version}-linux-x64.tar.gz`
3. Run: `cd {self.app_name}-{self.version}-linux-x64 && ./install.sh`
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

**Full Changelog**: [v0.9.0...v{self.version}](https://github.com/yourusername/VideoDownloader/compare/v0.9.0...v{self.version})
"""
        
        release_notes_path = self.release_dir / "RELEASE_NOTES.md"
        with open(release_notes_path, 'w') as f:
            f.write(release_notes)
        
        self.log(f"Created release notes: {release_notes_path}")
        return release_notes_path
    
    def create_github_release_template(self):
        """Create GitHub release template."""
        template = f"""# 🎬 HLS Video Downloader v{self.version}

A powerful, cross-platform tool for downloading HLS and HTTP video streams with a beautiful GUI.

## 🚀 Quick Install

### Windows
Download `{self.app_name}-{self.version}-windows-x64.zip` → Extract → Run `install.bat`

### macOS  
Download `{self.app_name}-{self.version}-darwin-universal.tar.gz` → Extract → Run `./install.sh`

### Linux
Download `{self.app_name}-{self.version}-linux-x64.tar.gz` → Extract → Run `./install.sh`

## ✨ What's New
- 🎯 One-click cross-platform installer
- 📦 Standalone executables (no Python required)
- 🖥️ Desktop integration with shortcuts
- 🧹 Clean uninstallation support
- 🔒 Virtual environment isolation

## 📋 System Requirements
- **Windows**: 7/8/10/11 (x64)
- **macOS**: 10.14+ (Universal)
- **Linux**: Ubuntu 18.04+ / Debian 10+ / CentOS 7+
- **Storage**: 200 MB free space
- **Network**: Internet connection for setup

## 📖 Documentation
- Installation guide included in each download
- See `INSTALLER_README.md` for detailed instructions
- Troubleshooting tips in platform-specific guides

## 🐛 Report Issues
Found a bug? [Create an issue](https://github.com/yourusername/VideoDownloader/issues/new)

---
**Note**: First-time users should download the platform-specific bundle for the easiest installation experience.
"""
        
        template_path = self.release_dir / "GITHUB_RELEASE_TEMPLATE.md"
        with open(template_path, 'w') as f:
            f.write(template)
        
        self.log(f"Created GitHub release template: {template_path}")
        return template_path
    
    def generate_checksums(self):
        """Generate SHA256 checksums for all release assets."""
        import hashlib
        
        checksums = {}
        checksum_file = self.release_dir / "SHA256SUMS.txt"
        
        with open(checksum_file, 'w') as f:
            f.write(f"# SHA256 Checksums for {self.app_name} v{self.version}\n")
            f.write(f"# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
            
            for file_path in self.release_dir.glob("*.zip"):
                sha256 = self.calculate_sha256(file_path)
                checksums[file_path.name] = sha256
                f.write(f"{sha256}  {file_path.name}\n")
            
            for file_path in self.release_dir.glob("*.tar.gz"):
                sha256 = self.calculate_sha256(file_path)
                checksums[file_path.name] = sha256
                f.write(f"{sha256}  {file_path.name}\n")
        
        self.log(f"Generated checksums: {checksum_file}")
        return checksums
    
    def calculate_sha256(self, file_path):
        """Calculate SHA256 hash of a file."""
        import hashlib
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    
    def prepare_release(self):
        """Main release preparation process."""
        self.log("🎬 Starting HLS Video Downloader Release Preparation")
        self.log("=" * 60)
        
        try:
            # Clean release directory
            self.clean_release_dir()
            
            # Generate platform bundle for current platform only
            # PyInstaller can't cross-compile, so we build for current platform
            created_bundles = []
            current_platform = self.current_platform
            if current_platform not in self.platforms:
                raise ValueError(f"Unsupported platform: {current_platform}")
            
            self.log(f"Building for current platform: {current_platform}")
            bundle_path = self.create_platform_bundle(current_platform)
            created_bundles.append(bundle_path)
            
            # Create documentation
            release_notes = self.create_release_notes()
            github_template = self.create_github_release_template()
            
            # Generate checksums
            checksums = self.generate_checksums()
            
            # Summary
            self.log("=" * 60)
            self.log("🎉 Release preparation completed successfully!")
            self.log(f"📁 Release assets: {self.release_dir}")
            self.log("📦 Created bundles:")
            
            total_size = 0
            for bundle in created_bundles:
                size_mb = bundle.stat().st_size / 1024 / 1024
                total_size += size_mb
                self.log(f"   • {bundle.name} ({size_mb:.1f} MB)")
            
            self.log(f"💾 Total size: {total_size:.1f} MB")
            self.log("📋 Documentation:")
            self.log(f"   • {release_notes.name}")
            self.log(f"   • {github_template.name}")
            self.log("🔐 Security:")
            self.log(f"   • SHA256SUMS.txt")
            self.log("=" * 60)
            self.log("🚀 Ready for GitHub release!")
            
            return True
            
        except Exception as e:
            self.log(f"❌ Release preparation failed: {e}", "ERROR")
            return False

def main():
    """Main entry point."""
    print("🎬 HLS Video Downloader - Release Preparator")
    print("=" * 60)
    
    preparator = ReleasePreparator()
    success = preparator.prepare_release()
    
    if success:
        print("\n🎯 Next Steps:")
        print("1. Review generated assets in release_assets/")
        print("2. Test bundles on target platforms")
        print("3. Commit and push your code")
        print("4. Create GitHub release using GITHUB_RELEASE_TEMPLATE.md")
        print("5. Upload all bundle files as release assets")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())