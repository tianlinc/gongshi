#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEI Timer Faster 服务版启动器

与 desktop/run.py 的区别：
  - 无 pywebview 桌面窗口，纯后台 Flask 服务
  - 无凭证记忆（/api/saved-credentials）
  - 无 /init 加载页
  - 无 CDN 改写（after_request 注入）
  - 端口冲突自动递增（5000 → 5001 → 5002）
  - 支持 GONGSHI_MIRROR_HOST 环境变量

开发模式（未打包）：
    python service_launcher.py

打包模式（PyInstaller）：
    IEI Timer Faster Service.exe
"""

import os
import sys
import shutil
import socket
import webbrowser
import threading as _threading


def _get_bundle_dir():
    """
    获取打包资源目录。

    PyInstaller 打包后：sys._MEIPASS（临时解压目录，只读）
    开发模式：项目根目录（service_launcher.py 的上一级）
    """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_data_dir():
    """
    获取用户数据目录。

    返回 %APPDATA%/gongshi/，确保 cache/ 子目录存在。
    该目录用于存储运行时产生的数据（任务缓存、节假日缓存等）。
    """
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
    data_dir = os.path.join(appdata, 'gongshi')
    os.makedirs(os.path.join(data_dir, 'cache'), exist_ok=True)
    return data_dir


def _seed_cache(bundle_dir, data_dir):
    """
    将打包内置的 cache 文件复制到用户数据目录。

    仅复制节假日缓存（holidays*.json），不复制用户任务缓存。
    用户任务缓存属于个人数据，不应预置。
    """
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


def _copy_prebuilt_browsers(bundle_dir, data_dir):
    """
    将预打包的 Playwright Chromium 浏览器复制到用户数据目录。

    INSPUR-52：打包时已预装 Chromium，用户启动后仅需本地文件复制，
    无需从 cdn.playwright.dev 下载，消除首次启动等待。

    复制为一次性操作（目标目录不存在时才复制），后续启动直接使用已有目录。
    返回 (ok: bool, was_copied: bool) — was_copied 表明本次是否执行了复制。
    """
    src = os.path.join(bundle_dir, 'playwright-browsers-prebuilt')
    dst = os.path.join(data_dir, 'playwright-browsers')
    if os.path.isdir(src) and not os.path.isdir(dst):
        print("[OK] 正在复制预置浏览器组件（约 655MB）...")
        try:
            shutil.copytree(src, dst)
            print("[OK] 浏览器组件复制完成 -> %s" % dst)
            # 完整性校验 — 确认完整 Chromium chrome.exe 真实存在
            chrome_exe_ok = False
            for d in os.listdir(dst):
                chrome_path = os.path.join(dst, d, 'chrome-win64', 'chrome.exe')
                if os.path.isfile(chrome_path):
                    chrome_exe_ok = True
                    break
            if not chrome_exe_ok:
                print("[X] 浏览器组件完整性校验失败: chrome.exe 缺失")
                print("    目标目录: %s" % dst)
                print("    目录内容: %s" % (os.listdir(dst) if os.path.isdir(dst) else '(目录不存在)'))
                return (False, False)
            print("[OK] 浏览器组件完整性校验通过")
            return (True, True)
        except Exception as e:
            print("[X] 浏览器组件复制失败: %s" % e)
            return (False, False)
    if os.path.isdir(dst):
        return (True, False)
    return (False, False)


def _find_available_port(start=5000, max_tries=3):
    """找一个可用端口，5000/5001/5002 依次尝试"""
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return None


def _setup_logging(data_dir):
    """将 stdout/stderr 重定向到日志文件（无控制台窗口时仍需保留日志）"""
    log_path = os.path.join(data_dir, 'run.log')
    if os.path.isfile(log_path) and os.path.getsize(log_path) > 1 * 1024 * 1024:
        os.remove(log_path)
    log_file = open(log_path, 'a', encoding='utf-8', buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file
    import logging as _logging
    _logging.basicConfig(
        stream=log_file, level=_logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
    )
    return log_path


def main():
    is_frozen = getattr(sys, 'frozen', False)

    bundle_dir = _get_bundle_dir()
    data_dir = _get_data_dir()

    if is_frozen:
        log_path = _setup_logging(data_dir)

    print("=" * 60)
    print("  IEI Timer Faster Service V1.0.0")
    print("=" * 60)
    if is_frozen:
        print(f"[OK] 日志文件: {log_path}")
    print(f"[OK] 数据目录: {data_dir}")

    # 初始化内置缓存文件
    _seed_cache(bundle_dir, data_dir)

    # 复制预打包 Chromium 浏览器（INSPUR-52）
    _prebuilt_ok, _prebuilt_copied = _copy_prebuilt_browsers(bundle_dir, data_dir)
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(data_dir, 'playwright-browsers')

    if _prebuilt_ok:
        if _prebuilt_copied:
            # 首次启动（刚复制完浏览器），验证可用性
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    p.chromium.launch(headless=True).close()
                print("[OK] 预打包浏览器组件验证通过")
            except Exception as e:
                print("[!] 预打包浏览器组件验证失败: %s" % e)
                _browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '(未设置)')
                print("    PLAYWRIGHT_BROWSERS_PATH = %s" % _browsers_path)
                if os.path.isdir(_browsers_path):
                    print("    目录内容: %s" % os.listdir(_browsers_path))
                else:
                    print("    目录不存在")
                _prebuilt_ok = False
        else:
            print("[OK] 浏览器组件已存在，跳过验证")

    # GONGSHI_MIRROR_HOST 环境变量支持
    mirror_host = os.environ.get('GONGSHI_MIRROR_HOST', '').strip()
    if mirror_host:
        os.environ['PLAYWRIGHT_DOWNLOAD_HOST'] = mirror_host.rstrip('/') + '/playwright-mirror/'
        print("[OK] 使用内网镜像: %s" % mirror_host)

    # 如果预打包浏览器不可用，尝试下载
    if not _prebuilt_ok:
        print("[!] 浏览器组件未就绪，尝试安装...")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                p.chromium.launch(headless=True).close()
            print("[OK] Chrome 浏览器组件已就绪")
        except Exception:
            print("[!] 首次运行，正在下载必要组件（约150MB，请耐心等待）...")
            import subprocess
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
                    print("[OK] 必要组件安装完成")
                else:
                    err = result.stderr.strip() or result.stdout.strip() or '(无输出)'
                    print(f"[X] 安装失败 (exit {result.returncode}): {err}")
                    print("[X] 浏览器组件未就绪，程序退出")
                    if is_frozen:
                        sys.exit(1)
                    else:
                        return
            except subprocess.TimeoutExpired:
                print("[X] 下载超时（超过 10 分钟），请检查网络后重试")
                if is_frozen:
                    sys.exit(1)
                else:
                    return
            except Exception as ex:
                print(f"[X] 安装异常: {ex}")
                if is_frozen:
                    sys.exit(1)
                else:
                    return

    # 确保能导入 app.py
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

    # 切换到数据目录（app.py 中 cache/ 路径相对于 CWD）
    os.chdir(data_dir)

    from app import app

    # 找可用端口
    port = _find_available_port(5000, 3)
    if port is None:
        print("[X] 端口 5000/5001/5002 均被占用，请关闭占用程序后重试")
        if is_frozen:
            sys.exit(1)
        else:
            return
    if port != 5000:
        print(f"[!] 5000 端口被占用，使用 {port}")

    url = f"http://127.0.0.1:{port}"
    print(f"[OK] 启动服务 {url} ...")
    print("    按 Ctrl+C 停止服务器")
    print()

    # 非服务模式（用户双击 exe）时自动打开浏览器，给用户即时反馈
    def _open_browser():
        import time
        time.sleep(1.5)
        try:
            webbrowser.open(url)
            print(f"[OK] 已打开浏览器 -> {url}")
        except Exception:
            pass  # 服务模式（Session 0）下打开浏览器会静默失败
    _threading.Thread(target=_open_browser, daemon=True).start()

    app.run(debug=False, host='127.0.0.1', port=port, use_reloader=False)


if __name__ == '__main__':
    main()
