# -*- mode: python ; coding: utf-8 -*-
"""
gongshi PyInstaller spec 文件
==============================
INSPUR-36: Windows 桌面程序打包（PyInstaller 方案）

技术选型结论（INSPUR-34 老王架构评审）：
  - 选 PyInstaller 而非 Nuitka：Playwright 兼容性成熟、构建快（分钟级）、
    体积 200-300MB 对内部小工具可接受
  - 输出格式：--onedir（目录模式），启动快于 --onefile

使用方法：
    cd desktop
    pyinstaller --clean --noconfirm gongshi.spec

构建产物：
    dist/IEI Timer Faster/IEI Timer Faster.exe  — 双击启动
"""

import os as _os
import sys as _sys

# -------------------- Playwright driver 路径 --------------------
# 关键：Playwright Python 包依赖一个 Node.js driver（playwright.cmd）。
# PyInstaller 不会自动收集非 .py 文件，需要 Tree() 显式打包。
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

# -------------------- Prebuilt Chromium (INSPUR-52) --------------------
# 将预安装的 Chromium 浏览器打包进 exe，消除首次启动下载等待。
# build.bat 会在打包前执行 playwright install chromium 到该目录。
# 如果目录不存在（手动构建），打包继续但 exe 首次启动时需下载。
_prebuilt_dir = 'playwright-browsers-prebuilt'
_prebuilt_datas = []
if _os.path.isdir(_prebuilt_dir):
    _prebuilt_datas.append((_prebuilt_dir, _prebuilt_dir))
    print("[OK] 已收集预打包 Chromium: %s" % _prebuilt_dir)
else:
    print("[!] 预打包 Chromium 目录不存在: %s（exe 首次启动时将下载）" % _prebuilt_dir)

# -------------------- Analysis --------------------
a = Analysis(
    ['run.py'],
    pathex=['..'],          # 确保 PyInstaller 能找到项目根目录的 app.py
    binaries=[],
    datas=[
        ('../templates', 'templates'),
        ('../static', 'static'),
        ('../cache', 'cache'),
    ] + _prebuilt_datas,
    hiddenimports=[
        # Flask 全家
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
        # Playwright（后台 headless 爬虫）
        'playwright',
        'playwright.sync_api',
        'playwright._impl._api_structures',
        'playwright._impl._browser_type',
        'playwright._impl._connection',
        'playwright._impl._object_factory',
        'playwright._impl._transport',
        # pywebview（桌面窗口，使用系统 Edge WebView2）
        'webview',
        'webview.platforms.winforms',
        'webview.js',
        'webview.util',
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
        # 排除不会用到的重型库，减小体积
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
        # 不压缩 Node.js 可执行文件，避免 corruption
        'playwright/driver/node.exe',
    ],
    runtime_tmpdir=None,
    console=False,  # 桌面应用模式，不显示 cmd 黑窗口
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
