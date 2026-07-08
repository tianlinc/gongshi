#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轻量版启动器 — 系统浏览器访问 http://localhost:5000

与 desktop/run.py 的区别：
  - 去掉 pywebview 桌面窗口，用户用系统自带浏览器访问
  - 去掉 Chromium 预打包（首次运行自动下载，约 150MB）
  - 去掉 /init 加载页、凭证记忆、CDN 改写
  - 端口冲突自动递增（5000 → 5001 → 5002）
  - 启动后自动打开默认浏览器
"""

import os
import sys
import shutil
import time
import threading
import subprocess
import webbrowser


def _get_bundle_dir():
    """PyInstaller 打包后返回 sys._MEIPASS，开发模式返回项目根目录"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_data_dir():
    """返回 %APPDATA%/gongshi/，确保 cache/ 子目录存在"""
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
    data_dir = os.path.join(appdata, 'gongshi')
    os.makedirs(os.path.join(data_dir, 'cache'), exist_ok=True)
    return data_dir


def _seed_cache(bundle_dir, data_dir):
    """将打包内置的节假日缓存复制到用户数据目录"""
    bundle_cache = os.path.join(bundle_dir, 'cache')
    user_cache = os.path.join(data_dir, 'cache')
    if not os.path.isdir(bundle_cache):
        return
    for fname in os.listdir(bundle_cache):
        if not fname.startswith('holidays') or not fname.endswith('.json'):
            continue
        src = os.path.join(bundle_cache, fname)
        dst = os.path.join(user_cache, fname)
        if os.path.isfile(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"[OK] 初始化节假日缓存: {fname}")


def _find_available_port(start=5000, max_tries=3):
    """找一个可用端口，5000/5001/5002 依次尝试"""
    import socket
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return None


def _ensure_chromium(data_dir):
    """检查 Playwright Chromium 是否可用，不可用则自动安装（支持镜像）"""
    browsers_dir = os.path.join(data_dir, 'playwright-browsers')
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir

    # 镜像配置
    mirror_host = os.environ.get('GONGSHI_MIRROR_HOST', '').strip()
    if mirror_host:
        host = mirror_host.rstrip('/') + '/playwright-mirror/'
        os.environ['PLAYWRIGHT_DOWNLOAD_HOST'] = host
        print(f"[OK] 使用内网镜像: {host}")

    # 试启动一次
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        print("[OK] Chromium 浏览器组件已就绪")
        return True
    except Exception:
        pass

    print("[!] 首次运行，正在下载 Chromium 浏览器组件（约 150MB，请耐心等待）...")
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'playwright', 'install', 'chromium'],
            capture_output=True, text=True, timeout=600,
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    print(f"  {line.strip()}")
        if result.returncode == 0:
            print("[OK] Chromium 安装完成")
            return True
        else:
            err = result.stderr.strip() or result.stdout.strip() or '(无输出)'
            print(f"[X] Chromium 安装失败 (exit {result.returncode}): {err}")
            return False
    except subprocess.TimeoutExpired:
        print("[X] 下载超时（超过 10 分钟），请检查网络后重试")
        return False
    except Exception as ex:
        print(f"[X] 安装异常: {ex}")
        return False


def main():
    bundle_dir = _get_bundle_dir()
    data_dir = _get_data_dir()

    print("=" * 60)
    print("  IEI Timer Faster V1.0.0 (轻量版)")
    print("=" * 60)
    print(f"[OK] 数据目录: {data_dir}")

    # 初始化缓存 + Chromium
    _seed_cache(bundle_dir, data_dir)
    if not _ensure_chromium(data_dir):
        print("[X] Chromium 浏览器组件未就绪，程序退出")
        sys.exit(1)

    # 确保能导入 app.py
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

    os.chdir(data_dir)
    from app import app

    # 找可用端口
    port = _find_available_port(5000, 3)
    if port is None:
        print("[X] 端口 5000/5001/5002 均被占用，请关闭占用程序后重试")
        sys.exit(1)
    if port != 5000:
        print(f"[!] 5000 端口被占用，使用 {port}")

    url = f'http://127.0.0.1:{port}'

    # 自动打开浏览器
    webbrowser.open(url)
    print("[OK] 正在启动服务，浏览器将自动打开...")
    print(f"     地址: {url}")
    print("     按 Ctrl+C 停止服务器")
    print()

    app.run(debug=False, host='127.0.0.1', port=port, use_reloader=False)


if __name__ == '__main__':
    main()
