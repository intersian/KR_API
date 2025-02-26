# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['overseas_monitor_2.py'],
    pathex=[],
    binaries=[],
    datas=[('.env', '.')],  # 설정 파일 포함
    hiddenimports=[
        'aiohttp',
        'websockets',
        'asyncio',
        'aiohttp.client_proto',
        'charset_normalizer.md__mypyc'
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
    name='해외주식모니터링2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None
) 