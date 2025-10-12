#!/usr/bin/env python3
"""
Build script for creating HLS Downloader executables using PyInstaller.
Supports Windows and macOS platforms.
"""

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

def get_platform_info():
    """Get platform-specific information."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == "windows":
        return "windows", "x64" if machine in ["amd64", "x86_64"] else "x86"
    elif system == "darwin":
        return "macos", "arm64" if machine == "arm64" else "x64"
    else:
        return system, machine

def clean_build_dirs():
    """Clean previous build directories."""
    dirs_to_clean = ["build", "dist", "__pycache__"]
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Cleaned {dir_name} directory")

def create_pyinstaller_spec():
    """Create PyInstaller spec file."""
    platform_name, arch = get_platform_info()
    
    # Platform-specific settings
    console_mode = 'True' if platform_name == 'windows' else 'False'
    icon_line = ''
    if platform_name == "windows" and os.path.exists("assets/icon.ico"):
        icon_line = 'icon="assets/icon.ico",'
    elif platform_name == "macos" and os.path.exists("assets/icon.icns"):
        icon_line = 'icon="assets/icon.icns",'
    
    bundle_section = ''
    if platform_name == "macos":
        if os.path.exists("assets/icon.icns"):
            bundle_section = 'app = BUNDLE(exe, name="HLS Downloader.app", icon="assets/icon.icns", bundle_identifier="com.hlsdownloader.app")'
        else:
            bundle_section = 'app = BUNDLE(exe, name="HLS Downloader.app", bundle_identifier="com.hlsdownloader.app")'
    
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('hlsdownloader', 'hlsdownloader'),
    ],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui', 
        'PyQt5.QtWidgets',
        'aiohttp',
        'aiohttp.web',
        'aiohttp.client',
        'playwright',
        'playwright.sync_api',
        'playwright.async_api',
        'asyncio',
        'concurrent.futures',
        'multiprocessing',
        'ssl',
        'certifi',
        'Crypto.Cipher.AES',
        'Crypto.Util.Padding',
    ],
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
    name='HLS Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console_mode},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    {icon_line}
)

{bundle_section}
'''
    
    with open("HLS-Downloader.spec", "w") as f:
        f.write(spec_content)
    
    return "HLS-Downloader.spec"

def build_executable():
    """Build the executable using PyInstaller."""
    platform_name, arch = get_platform_info()
    
    print(f"Building HLS Downloader for {platform_name} {arch}")
    print("=" * 50)
    
    # Clean previous builds
    clean_build_dirs()
    
    # Create spec file
    spec_file = create_pyinstaller_spec()
    print(f"Created spec file: {spec_file}")
    
    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        spec_file
    ]
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Build completed successfully!")
        print(result.stdout)
        
        # Create release directory
        release_dir = Path("release")
        release_dir.mkdir(exist_ok=True)
        
        # Copy built executable
        if platform_name == "windows":
            src = Path("dist/HLS Downloader.exe")
            dst = release_dir / f"HLS-Downloader-{platform_name}-{arch}.exe"
        elif platform_name == "macos":
            src = Path("dist/HLS Downloader.app")
            dst = release_dir / f"HLS-Downloader-{platform_name}-{arch}.app"
            if src.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)
                print(f"Copied app bundle to {dst}")
                
                # Try to code sign if developer identity is available
                try:
                    # Check if we have a signing identity
                    result = subprocess.run(
                        ["security", "find-identity", "-v", "-p", "codesigning"],
                        capture_output=True, text=True
                    )
                    if "Developer ID Application" in result.stdout:
                        print("Code signing the app bundle...")
                        subprocess.run([
                            "codesign", "--force", "--deep", "--sign", 
                            "Developer ID Application", str(dst)
                        ], check=True)
                        print("App bundle signed successfully!")
                    else:
                        print("No Developer ID found. App will show security warnings.")
                        print("To fix this, get an Apple Developer account and certificate.")
                except Exception as e:
                    print(f"Code signing failed: {e}")
                    print("App will show security warnings when downloaded.")
                
                return
        else:
            src = Path("dist/HLS Downloader")
            dst = release_dir / f"HLS-Downloader-{platform_name}-{arch}"
        
        if src.exists():
            shutil.copy2(src, dst)
            print(f"Copied executable to {dst}")
        else:
            print(f"Warning: Built executable not found at {src}")
            
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error: {e}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        sys.exit(1)

def main():
    """Main function."""
    if len(sys.argv) > 1 and sys.argv[1] == "--clean":
        clean_build_dirs()
        return
    
    # Check if required dependencies are installed
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    build_executable()

if __name__ == "__main__":
    main()