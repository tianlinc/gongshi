# -*- mode: python ; coding: utf-8 -*-
"""
gongshi 桌面版 PyInstaller spec 文件（原服务版改造）
=====================================================
INSPUR-74: 从 Windows 后台服务（NSSM）改造为独立桌面应用。

与改造前的区别：
  - 入口：service_launcher.py（已是 pywebview 桌面启动器）
  - 新增 pywebview/webview hiddenimports（WebView2 桌面窗口）
  - 不再排除 webview/pythonnet
  - console=False（桌面应用模式，无控制台窗口）
  - 输出名：IEI Timer Faster（非 Service）

使用方法：
    cd service_installer
    pyinstaller --noconfirm service.spec

构建产物：
    dist/IEI Timer Faster/IEI Timer Faster.exe
"""

import os as _os
import sys as _sys

# -------------------- Analysis --------------------
a = Analysis(
    ['service_launcher.py'],
    pathex=['..'],          # 确保 PyInstaller 能找到项目根目录的 app.py
    binaries=[],
    datas=[
        ('../templates', 'templates'),
        ('../static', 'static'),
        ('../cache', 'cache'),
        ('../VERSION', '.'),  # INSPUR-82: VERSION 文件打包到产物根目录
    ],
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
        # pywebview（桌面窗口，按平台选后端）
        'webview',
        'webview.platforms.cocoa' if _sys.platform == 'darwin' else 'webview.platforms.winforms',
        'webview.js',
        'webview.util',
        # 本地模块
        'license_utils',
        '_desktop_common',
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
        # cefpython3: 已废弃的 CEF 后端（仅 Edge WebView2 使用中）
        #   108MB，占 _internal 目录 68%，完全不必要
        'cefpython3',
        # Pythonwin: pywin32 IDE 工具，非运行时依赖 (6.5MB)
        'Pythonwin',
    ],
)

# -------------------- PYZ --------------------
pyz = PYZ(a.pure, a.zipped_data)

# macOS: EXE 名必须与 COLLECT 名不同，避免文件/目录同名冲突
#   Windows: ai_timer.exe (文件) vs IEI Timer Faster/ (目录) → 无冲突（扩展名不同）
#   macOS:   ai_timer (文件) vs IEI Timer Faster/ (目录) → 冲突，必须改名
_exe_name = 'ai_timer' if _sys.platform == 'darwin' else 'IEI Timer Faster'

# -------------------- EXE --------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=_exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 桌面应用模式，不显示 cmd 黑窗口 (macOS: .app bundle)
    icon='iei_timer.icns' if _sys.platform == 'darwin' and _os.path.exists('iei_timer.icns') else 'iei_timer.ico',
)

# -------------------- COLLECT（onedir 模式）--------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='IEI Timer Faster',
)

# -------------------- BUNDLE（仅 macOS：创建 .app 包）--------------------
if _sys.platform == 'darwin':
    _icon = 'iei_timer.icns' if _os.path.exists('iei_timer.icns') else None
    # INSPUR-82: 从 VERSION 文件读取版本号用于 macOS Bundle
    _ver_path = _os.path.join(_os.path.dirname(SPECPATH), '..', 'VERSION')
    try:
        with open(_os.path.normpath(_ver_path), 'r', encoding='utf-8') as _vf:
            _bundle_ver = _vf.read().strip()
    except Exception:
        _bundle_ver = '1.0.0'
    app = BUNDLE(
        coll,
        name='IEI Timer Faster.app',
        icon=_icon,
        bundle_identifier='com.inmanage.ieitimer',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSMinimumSystemVersion': '10.13',
            'CFBundleShortVersionString': _bundle_ver,
            'CFBundleVersion': _bundle_ver,
        },
    )
