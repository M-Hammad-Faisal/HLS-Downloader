# -*- mode: python ; coding: utf-8 -*-

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
    hooksconfig={},
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.icns",
)

app = BUNDLE(exe, name="HLS Downloader.app", icon="assets/icon.icns", bundle_identifier="com.hlsdownloader.app")
