# -*- mode: python ; coding: utf-8 -*-
"""
轻量版 PyInstaller spec 文件
=============================
与 desktop/gongshi.spec 的区别：
  - 去掉 pywebview 桌面窗口依赖
  - 去掉 Chromium 预打包（首次运行自动下载）
  - 入口：launcher.py 替代 run.py
  - console=True：显示控制台输出（用户可看到启动日志）

使用方法：
    cd lightweight
    pyinstaller --clean --noconfirm lightweight.spec

构建产物：
    dist/IEI Timer Faster/IEI Timer Faster.exe  — 双击启动
"""

import os as _os
import sys as _sys

# -------------------- Playwright driver 路径 --------------------
try:
    import playwright
    _pw_dir = _os.path.dirname(playwright.__file__)
    _driver_dir = _os.path.join(_pw_dir, 'driver')
    if not _os.path.isdir(_driver_dir):
        print(f"[!] Playwright driver 目录不存在: {_driver_dir}")
        _driver_dir = None
except ImportError:
    print("[!] Playwright 未安装，driver 不会被收集（exe 首次启动时将自动安装 Chromium）")
    _driver_dir = None

# -------------------- Analysis --------------------
a = Analysis(
    ['launcher.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../templates', 'templates'),
        ('../static', 'static'),
        ('../cache', 'cache'),
    ],
    hiddenimports=[
        # Flask
        'flask',
        'flask_cors',
        'jinja2.ext',
        # 加密
        'Crypto.Cipher.AES',
        'Crypto.Cipher._mode_ecb',
        'Crypto.Util.Padding',
        # HTTP / 解析
        'requests',
        'bs4',
        'bs4.builder._html5lib',
        'bs4.builder._htmlparser',
        # Playwright（headless 爬虫 — 首次运行下载 Chromium）
        'playwright',
        'playwright.sync_api',
        'playwright._impl._api_structures',
        'playwright._impl._browser_type',
        'playwright._impl._connection',
        'playwright._impl._object_factory',
        'playwright._impl._transport',
        # 本地模块
        'license_utils',
        # 标准库常被遗漏的
        'html',
        'json',
        're',
        'logging',
        'threading',
        'urllib.parse',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
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
    ],
)

# 收集 Playwright driver（Node.js 可执行文件 + node_modules）
if _driver_dir:
    a.datas += Tree(_driver_dir, prefix='playwright/driver')
    print(f"[OK] 已收集 Playwright driver: {_driver_dir}")

# -------------------- PYZ --------------------
pyz = PYZ(a.pure, a.zipped_data)

# -------------------- EXE --------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='IEI Timer Faster',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'playwright/driver/node.exe',
    ],
    runtime_tmpdir=None,
    console=True,  # 轻量版显示控制台，用户可看到启动日志
)

# -------------------- COLLECT（onedir 模式）--------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['playwright/driver/node.exe'],
    name='IEI Timer Faster',
)
