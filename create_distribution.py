#!/usr/bin/env python3
"""
Create distribution package for HLS Video Downloader
Packages the installer and application files for easy distribution.
"""

import os
import sys
import shutil
import zipfile
import tarfile
from pathlib import Path
import platform

def create_distribution():
    """Create distribution packages for different platforms."""
    
    print("🎬 Creating HLS Video Downloader Distribution Package")
    print("=" * 60)
    
    # Get current directory and version
    current_dir = Path.cwd()
    version = "1.0.0"
    app_name = "HLS-Video-Downloader"
    
    # Create dist directory
    dist_dir = current_dir / "dist"
    dist_dir.mkdir(exist_ok=True)
    
    # Files to include in distribution
    files_to_include = [
        "installer.py",
        "install.bat",
        "install.sh", 
        "INSTALLER_README.md",
        "hlsdownloader/",
        "main.py",
        "requirements.txt",
        "assets/",
        "build_executable.py",
        "HLS-Downloader.spec",
        "README.md",
        "LICENSE"
    ]
    
    # Create temporary directory for packaging
    temp_dir = dist_dir / f"{app_name}-{version}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    print(f"📁 Preparing files in: {temp_dir}")
    
    # Copy files to temp directory
    for item in files_to_include:
        src = current_dir / item
        if src.exists():
            dst = temp_dir / item
            if src.is_dir():
                shutil.copytree(src, dst)
                print(f"✅ Copied directory: {item}")
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                print(f"✅ Copied file: {item}")
        else:
            print(f"⚠️  Warning: {item} not found, skipping")
    
    # Create platform-specific packages
    system = platform.system().lower()
    
    # Create ZIP package (universal)
    zip_name = f"{app_name}-{version}.zip"
    zip_path = dist_dir / zip_name
    
    print(f"\n📦 Creating ZIP package: {zip_name}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(temp_dir)
                zipf.write(file_path, arcname)
    
    print(f"✅ ZIP package created: {zip_path}")
    print(f"📊 Size: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Create TAR.GZ package (for Unix systems)
    if system in ['darwin', 'linux']:
        tar_name = f"{app_name}-{version}.tar.gz"
        tar_path = dist_dir / tar_name
        
        print(f"\n📦 Creating TAR.GZ package: {tar_name}")
        with tarfile.open(tar_path, 'w:gz') as tarf:
            tarf.add(temp_dir, arcname=f"{app_name}-{version}")
        
        print(f"✅ TAR.GZ package created: {tar_path}")
        print(f"📊 Size: {tar_path.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Create installation instructions
    instructions_file = dist_dir / "INSTALLATION_INSTRUCTIONS.txt"
    instructions_content = f"""
HLS Video Downloader v{version} - Installation Instructions
=========================================================

QUICK START:
-----------
1. Extract this archive to any folder
2. Run the installer for your platform:
   - Windows: Double-click "install.bat"
   - macOS/Linux: Run "./install.sh" in terminal

WHAT'S INCLUDED:
---------------
- installer.py: Smart installer script
- install.bat: Windows installer launcher
- install.sh: macOS/Linux installer launcher
- INSTALLER_README.md: Detailed installation guide
- hlsdownloader/: Application source code
- main.py: Application entry point
- requirements.txt: Python dependencies
- assets/: Application assets and icons

SYSTEM REQUIREMENTS:
-------------------
- Python 3.8 or higher
- 4 GB RAM (8 GB recommended)
- 2 GB free disk space
- Internet connection (for initial setup)

SUPPORTED PLATFORMS:
-------------------
- Windows 10/11
- macOS 10.14+
- Linux (Ubuntu 18.04+, CentOS 7+)

FEATURES:
---------
- Download HLS (HTTP Live Streaming) videos
- Download regular HTTP video files
- Browser automation for JavaScript-heavy sites
- Multiple resolution options
- Concurrent downloads
- User-friendly GUI and CLI interfaces

For detailed instructions, see INSTALLER_README.md

Support: Check the README.md file for troubleshooting tips.
"""
    
    with open(instructions_file, 'w') as f:
        f.write(instructions_content)
    
    print(f"\n📄 Installation instructions created: {instructions_file}")
    
    # Clean up temp directory
    shutil.rmtree(temp_dir)
    
    print("\n" + "=" * 60)
    print("🎉 Distribution packages created successfully!")
    print(f"📁 Location: {dist_dir}")
    print("\nPackages created:")
    for file in dist_dir.glob("*.zip"):
        print(f"  📦 {file.name} ({file.stat().st_size / 1024 / 1024:.1f} MB)")
    for file in dist_dir.glob("*.tar.gz"):
        print(f"  📦 {file.name} ({file.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  📄 {instructions_file.name}")
    print("\nReady for distribution! 🚀")

if __name__ == "__main__":
    try:
        create_distribution()
    except KeyboardInterrupt:
        print("\n\n⚠️  Package creation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error creating distribution: {e}")
        sys.exit(1)