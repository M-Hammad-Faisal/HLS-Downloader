# -*- mode: python ; coding: utf-8 -*-
"""
Optimized PyInstaller spec file for HLS Downloader
Reduces application size by excluding unnecessary modules and optimizing the build.
"""

import sys
from pathlib import Path

# Get the current directory
current_dir = Path.cwd()

# Define excluded modules to reduce size (conservative list to avoid conflicts)
excluded_modules = [
    # Exclude unused GUI modules (we only need PyQt5)
    'tkinter',
    'turtle',
    
    # Exclude unused test modules
    'unittest',
    'doctest',
    
    # Exclude unused network modules
    'ftplib',
    'poplib',
    'imaplib',
    'nntplib',
    'smtplib',
    'telnetlib',
    
    # Exclude unused multimedia
    'audioop',
    'wave',
    'sunau',
    'aifc',
    
    # Exclude unused system modules
    'pty',
    'tty',
]

a = Analysis(
    ['main.py'],
    pathex=[str(current_dir)],
    binaries=[],
    datas=[
        ('assets/icon.icns', 'assets'),
        ('assets/icon.ico', 'assets'),
    ],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtWidgets', 
        'PyQt5.QtGui',
        'playwright',
        'playwright._impl',
        'aiohttp',
        'Crypto.Cipher.AES',
        'Crypto.Util.Padding',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# Remove duplicate entries and optimize
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Create the executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HLS Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Strip debug symbols to reduce size
    upx=True,    # Use UPX compression
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.icns' if sys.platform == 'darwin' else 'assets/icon.ico',
)

# Create the distribution directory
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,   # Strip debug symbols from binaries
    upx=True,     # Compress binaries with UPX
    upx_exclude=[],
    name='HLS Downloader',
)

# Create macOS app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='HLS Downloader.app',
        icon='assets/icon.icns',
        bundle_identifier='com.hlsdownloader.app',
        info_plist={
            'CFBundleName': 'HLS Downloader',
            'CFBundleDisplayName': 'HLS Downloader',
            'CFBundleVersion': '2.0.4',
            'CFBundleShortVersionString': '2.0.4',
            'CFBundleIdentifier': 'com.hlsdownloader.app',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.14.0',
            'NSRequiresAquaSystemAppearance': False,
        },
    )