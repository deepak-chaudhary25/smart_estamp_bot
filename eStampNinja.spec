# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\1. DEVELOPMENT\\smart_estamp\\estamp_auto.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\1. DEVELOPMENT\\smart_estamp\\icon.png', '.'), ('C:\\1. DEVELOPMENT\\smart_estamp\\config.py', '.')],
    hiddenimports=['playwright', 'playwright.sync_api'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='eStampNinja',
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
    icon=['C:\\1. DEVELOPMENT\\smart_estamp\\icon.ico'],
)
