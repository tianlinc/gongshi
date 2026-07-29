# -*- mode: python ; coding: utf-8 -*-
"""
gongshi bootstrap 启动器 — PyInstaller spec 文件
==================================================
INSPUR-102: 独立引导启动器，负责在应用启动前处理增量更新。
INSPUR-112: 添加 tkinter 升级进度窗口。

编译为 onefile exe（~14-18MB含 tkinter），与主应用同目录。
启动时检查 update_ready.json，显示升级进度窗口（tkinter GUI），
完成后自动启动主应用 IEI Timer Faster.exe。

使用方法：
    cd service_installer
    pyinstaller --noconfirm bootstrap.spec

构建产物：
    dist/bootstrap.exe
"""

import os as _os
import sys as _sys

# -------------------- Analysis --------------------
a = Analysis(
    ['../_bootstrap.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'json',
        'hashlib',
        'shutil',
        'subprocess',
        'traceback',
        'queue',
        # INSPUR-112: tkinter for upgrade progress window
        'tkinter',
        'tkinter.ttk',
        '_tkinter',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'cv2',
        'scipy',
        'sqlalchemy',
        'django',
        'IPython',
        'jupyter',
        'notebook',
        'cefpython3',
        'Pythonwin',
        'flask',
        'flask_cors',
        'jinja2',
        'requests',
        'bs4',
        'webview',
        'certifi',
        'Crypto',
    ],
)

# -------------------- PYZ --------------------
pyz = PYZ(a.pure, a.zipped_data)

# -------------------- EXE (onefile) --------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='bootstrap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无黑窗口
    icon='iei_timer.ico',
)
