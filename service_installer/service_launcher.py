#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEI Timer Faster 桌面版启动器

INSPUR-74: 从 Windows 后台服务（NSSM）改造为独立桌面应用。
用户双击快捷方式即可在 WebView2 窗口中访问，无需系统浏览器。

特性:
  - 端口冲突自动递增（5000 → 5001 → 5002）
  - 仅 WebView2（无 CEF 后端）
  - 共享逻辑提取到 _desktop_common.py

开发模式（未打包）：
    python service_launcher.py         # debug=True + webbrowser（调试用）

打包模式（PyInstaller）：
    IEI Timer Faster.exe               # debug=False + pywebview 独立桌面窗口

INSPUR-109: 启动时检查 update_ready.json 并应用增量更新。
由于 PyInstaller onedir 模式下 bootstrap.exe 未构建，需要在这里完成
增量更新的应用流程——在导入业务模块前执行，避免文件锁冲突。
"""

import os
import sys

# =========================================================================
# INSPUR-109: 启动时检查并应用待处理增量更新
# =========================================================================
# 必须在导入任何业务模块前执行，避免 _internal/ 中 Python 模块被加载后
# 文件被锁导致无法覆盖。标准库（os/sys/json/shutil/subprocess）安全。


def _maybe_apply_update():
    """检查 update_ready.json 并应用增量更新。

    仅在 PyInstaller frozen 模式下触发。开发模式跳过。
    增量更新：应用 staging 目录文件，成功后重启 exe 以加载新代码。
    完整包：运行 Inno Setup 静默安装器（batch 脚本机制）。

    异常和失败时不抛错——清理 update_ready.json 后正常启动旧版本。
    """
    if not getattr(sys, 'frozen', False):
        return  # 开发模式，跳过

    appdata = os.environ.get('APPDATA', '')
    if not appdata:
        return

    data_dir = os.path.join(appdata, 'gongshi')
    update_ready = os.path.join(data_dir, 'update_ready.json')

    if not os.path.isfile(update_ready):
        return

    import json
    try:
        with open(update_ready, 'r', encoding='utf-8') as f:
            update_info = json.load(f)
    except Exception:
        _cleanup_update_ready(update_ready)
        return

    update_type = update_info.get('type', '')

    if update_type == 'incremental':
        _apply_incremental_update(update_info, update_ready)
    elif update_type == 'full':
        _apply_full_update(update_info, update_ready)
    else:
        # 未知类型，清理后正常启动
        _cleanup_update_ready(update_ready)


def _cleanup_update_ready(path):
    """安全删除 update_ready.json（静默忽略失败）。"""
    try:
        os.remove(path)
    except Exception:
        pass


def _apply_incremental_update(update_info, update_ready_path):
    """应用增量 staging 更新并重启 exe 以加载新代码。

    导入 _bootstrap 模块执行 staging → app 目录的文件替换，
    成功后通过 subprocess 重启自身（新版文件生效），
    失败时清理 update_ready.json 避免无限重启循环。
    """
    import logging as _log
    try:
        import _bootstrap
    except ImportError:
        _log.error("[X] INSPUR-109: _bootstrap 模块不可用，无法应用增量更新")
        return  # 保留 update_ready.json，下次启动再试

    try:
        success = _bootstrap._apply_staging(update_info)
    except Exception as e:
        _log.error("[X] INSPUR-109: 应用增量更新异常: %s", e)
        success = False

    if success:
        _log.info("[OK] INSPUR-109: 增量更新已应用，重启加载新代码...")
        import subprocess
        subprocess.Popen(
            [sys.executable],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        sys.exit(0)
    else:
        # 失败时清理 update_ready.json，避免每次启动都尝试失败的更新
        _cleanup_update_ready(update_ready_path)


def _apply_full_update(update_info, update_ready_path):
    """完整包安装：运行 Inno Setup 静默安装器。

    与 _desktop_common.restart_and_install() 逻辑一致，
    通过 batch 脚本在独立进程中执行安装（避免文件锁问题）。
    """
    _cleanup_update_ready(update_ready_path)

    installer_path = update_info.get('installer_path', '')
    if not installer_path or not os.path.isfile(installer_path):
        return

    import subprocess

    # 确定安装目标目录
    frozen_dir = os.path.dirname(sys.executable)
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
            r'\{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}_is1'
        )
        try:
            val, _ = winreg.QueryValueEx(key, 'InstallLocation')
            install_dir = val if (val and os.path.isdir(val)) else None
        finally:
            winreg.CloseKey(key)
    except OSError:
        install_dir = None

    target_dir = install_dir or os.path.join(
        os.environ.get('LOCALAPPDATA', ''), 'IEI Timer Faster')

    bat_path = os.path.join(os.path.dirname(installer_path), '_install.bat')
    log_file = os.path.join(os.path.dirname(installer_path), '_update.log')

    bat_lines = [
        '@echo off',
        'setlocal enabledelayedexpansion',
        f'set LOG={log_file}',
        '',
        f'echo [!date! !time!] 开始更新... >> "!LOG!"',
        '',
        'taskkill /f /im "IEI Timer Faster.exe" >nul 2>&1',
        f'echo [!date! !time!] 已终止旧进程 >> "!LOG!"',
        '',
        'ping 127.0.0.1 -n 3 >nul',
        '',
        f'echo [!date! !time!] 运行安装程序... >> "!LOG!"',
        f'"{installer_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="{target_dir}"',
        'set SETUP_ERR=!ERRORLEVEL!',
        '',
        'if !SETUP_ERR! neq 0 (',
        f'    echo [!date! !time!] [X] 安装失败, 错误码=!SETUP_ERR! >> "!LOG!"',
        '    exit /b !SETUP_ERR!',
        ')',
        '',
        f'echo [!date! !time!] [OK] 安装成功 >> "!LOG!"',
        f'echo [!date! !time!] 启动新版本... >> "!LOG!"',
        f'start "" "{os.path.join(target_dir, "IEI Timer Faster.exe")}"',
        '',
        f'echo [!date! !time!] 清理临时文件... >> "!LOG!"',
        f'del /f /q "{installer_path}" >nul 2>&1',
        f'del /f /q "{bat_path}" >nul 2>&1',
        f'echo [!date! !time!] 更新流程完成 >> "!LOG!"',
    ]

    with open(bat_path, 'w', encoding='gbk') as f:
        f.write('\r\n'.join(bat_lines))

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    subprocess.Popen(
        ['cmd.exe', '/c', bat_path],
        startupinfo=startupinfo,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    sys.exit(0)


_maybe_apply_update()

# 确保项目根目录可导入 _desktop_common（dev 模式需要）
if not getattr(sys, 'frozen', False):
    _proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _proj_root not in sys.path:
        sys.path.insert(0, _proj_root)

from _desktop_common import DesktopLauncher


def main():
    DesktopLauncher(port=5000, port_auto=True, enable_cef=False).run()


if __name__ == '__main__':
    main()
