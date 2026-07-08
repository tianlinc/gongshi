# -*- mode: python ; coding: utf-8 -*-
"""
gongshi 服务版 PyInstaller spec 文件
======================================
INSPUR-65: Windows 服务版打包（PyInstaller 方案）

与 desktop/gongshi.spec 的区别：
  - 入口：service_launcher.py（非 run.py）
  - console=False（服务模式，无控制台窗口）
  - 移除 pywebview/webview 相关 hiddenimports
  - 移除 pythonnet/Pythonwin/pywin32_system32 相关
  - 输出名：IEI Timer Faster Service

技术选型：
  - PyInstaller onedir（就像 desktop/ 方案）
  - Chromium 预打包（无 pywebview）
  - 源码编译为 .pyc，用户不可见

使用方法：
    cd service_installer
    pyinstaller --noconfirm service.spec

构建产物：
    dist/IEI Timer Faster Service/IEI Timer Faster Service.exe
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

# -------------------- Prebuilt Chromium (INSPUR-52) --------------------
# Try multiple possible prebuilt Chromium locations:
#   1) service_installer/ local (created by build.bat step)
#   2) desktop/ prebuilt (reuse existing)
_prebuilt_candidates = [
    'playwright-browsers-prebuilt',
    '../desktop/playwright-browsers-prebuilt',
]
_prebuilt_dir = None
_prebuilt_datas = []
for _candidate in _prebuilt_candidates:
    if _os.path.isdir(_candidate):
        _prebuilt_dir = _candidate
        # Map to 'playwright-browsers-prebuilt' in bundle regardless of source path
        # so service_launcher.py can find it at the canonical bundle path
        _prebuilt_datas.append((_candidate, 'playwright-browsers-prebuilt'))
        print("[OK] 已收集预打包 Chromium: %s" % _candidate)
        break
if not _prebuilt_datas:
    print("[!] 预打包 Chromium 目录不存在")
    print("    运行 build.bat 自动准备，或手动执行:")
    print("      set PLAYWRIGHT_BROWSERS_PATH=%%CD%%\\playwright-browsers-prebuilt")
    print("      python -m playwright install chromium")
    print("    构建将继续，但产物不含预打包 Chromium (首次启动需联网下载)")

# -------------------- Analysis --------------------
a = Analysis(
    ['service_launcher.py'],
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
        # 服务版不需要桌面窗口相关
        'webview',
        'pythonnet',
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
    name='IEI Timer Faster Service',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'playwright/driver/node.exe',
    ],
    runtime_tmpdir=None,
    console=False,  # 服务模式，不显示 cmd 黑窗口
    icon='iei_timer.ico',
)

# -------------------- COLLECT（onedir 模式）--------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['playwright/driver/node.exe'],
    name='IEI Timer Faster Service',
)
