#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEI Timer Faster 桌面版启动器

PyInstaller 打包入口脚本。负责：
  - 初始化用户数据目录（%APPDATA%/gongshi/）
  - 从打包资源中复制内置缓存文件（节假日数据）
  - INSPUR-52：复制预打包 Playwright Chromium 浏览器（消除首次启动下载等待）
  - 设置 Playwright 浏览器路径
  - 启动 Flask 应用并显示独立桌面窗口

桌面窗口：使用 Windows 自带 Edge WebView2 引擎，不依赖系统浏览器。
Playwright Chromium：仅在后台 headless 爬取 RDM 任务列表时使用，用户不可见。
Chromium 预打包（INSPUR-52）：构建时预装到 playwright-browsers-prebuilt/，
首次启动仅需文件复制（秒级），无需从 cdn.playwright.dev 下载。

开发模式（未打包）：
    python run.py          # debug=True + webbrowser（方便热重载调试）

打包模式（PyInstaller）：
    IEI Timer Faster.exe   # debug=False + 独立桌面窗口
"""

import os
import sys
import shutil
import time
import threading
import json
import base64


# ---------- 凭证持久化（本地 AES 加密，复用 app.py 的加密栈）----------

_CRED_AES_KEY = b'gongshi_desk_202'  # 固定 16 字节 AES key


def _save_credentials(data_dir, username, password):
    """AES-ECB 加密保存凭证"""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    path = os.path.join(data_dir, 'credentials.dat')
    payload = json.dumps({'u': username, 'p': password})
    cipher = AES.new(_CRED_AES_KEY, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(payload.encode('utf-8'), AES.block_size))
    with open(path, 'wb') as f:
        f.write(base64.b64encode(encrypted))
    print(f"[OK] 凭证已加密保存 -> {path}")


def _load_credentials(data_dir):
    """AES-ECB 解密凭证，失败返回 (None, None)"""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    path = os.path.join(data_dir, 'credentials.dat')
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, 'rb') as f:
            encrypted = base64.b64decode(f.read())
        cipher = AES.new(_CRED_AES_KEY, AES.MODE_ECB)
        decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)
        data = json.loads(decrypted.decode('utf-8'))
        return data.get('u'), data.get('p')
    except Exception as e:
        print(f"[X] 凭证解密失败: {e}")
        return None, None


def _delete_credentials(data_dir):
    """删除本地凭证文件"""
    path = os.path.join(data_dir, 'credentials.dat')
    if os.path.isfile(path):
        os.remove(path)
        print("[OK] 凭证已删除")


def _get_bundle_dir():
    """
    获取打包资源目录。

    PyInstaller 打包后：sys._MEIPASS（临时解压目录，只读）
    开发模式：项目根目录（run.py 的上一级）
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
        # 只种节假日，跳过任务缓存文件
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
    返回 (ok: bool, was_copied: bool) — was_copied 表明本次是否执行了复制，
    调用方应仅在 was_copied=True 时做启动验证，后续启动跳过验证以加快启动速度。
    """
    src = os.path.join(bundle_dir, 'playwright-browsers-prebuilt')
    dst = os.path.join(data_dir, 'playwright-browsers')
    if os.path.isdir(src) and not os.path.isdir(dst):
        print("[OK] 正在复制预置浏览器组件（约 655MB）...")
        try:
            shutil.copytree(src, dst)
            print("[OK] 浏览器组件复制完成 -> %s" % dst)
            # INSPUR-53: 完整性校验 — 确认完整 Chromium chrome.exe 真实存在
            # 杀毒软件/磁盘满/复制中断都可能导致文件缺失
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
        # 已有浏览器，无需复制或验证
        return (True, False)
    return (False, False)


def _ensure_playwright_browsers(data_dir):
    """
    检查 Playwright Chromium（headless 后台爬虫用）是否可用。

    注意：这里的 Chromium 是 Playwright 专用的 headless 浏览器，
    用于后台爬取 RDM 任务列表，用户看不到。跟桌面窗口用的 WebView2
    是完全不同的两个东西。

    PyInstaller 打包模式：使用捆绑的 Node.js + playwright CLI 安装。
    开发模式：使用系统 Python 的 playwright 模块安装。

    INSPUR-51：支持 GONGSHI_MIRROR_HOST 环境变量，将下载重定向到内网镜像。
    返回 (success: bool, error_message: str)
    """
    browsers_dir = os.path.join(data_dir, 'playwright-browsers')
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir

    # INSPUR-51: 内网镜像重定向
    mirror_host = os.environ.get("GONGSHI_MIRROR_HOST", "").strip()
    mirror_info = ""
    if mirror_host:
        os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = mirror_host.rstrip("/") + "/playwright-mirror/"
        mirror_info = "（镜像: %s）" % mirror_host
        print("[OK] 使用内网镜像: %s" % os.environ["PLAYWRIGHT_DOWNLOAD_HOST"])

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("[OK] 必要组件已就绪")
        return (True, "")
    except Exception:
        if mirror_info:
            print("[!] 首次运行，正在下载必要组件（约150MB，请耐心等待）...%s" % mirror_info)
        else:
            print("[!] 首次运行，正在下载必要组件（约150MB，请耐心等待）...")

        import subprocess

        if getattr(sys, 'frozen', False):
            # PyInstaller 打包模式：使用捆绑的 Node.js + playwright CLI
            driver_dir = os.path.join(sys._MEIPASS, 'playwright', 'driver')
            node_exe = os.path.join(driver_dir, 'node.exe')
            cli_js = os.path.join(driver_dir, 'package', 'cli.js')

            if not os.path.isfile(node_exe):
                print(f"[X] Node.js 未找到: {node_exe}")
                return (False, f"Node.js 未找到: {node_exe}")
            if not os.path.isfile(cli_js):
                print(f"[X] playwright CLI 未找到: {cli_js}")
                return (False, f"playwright CLI 未找到: {cli_js}")

            print(f"[OK] 使用捆绑 CLI 安装...")
            try:
                result = subprocess.run(
                    [node_exe, cli_js, 'install', 'chromium'],
                    capture_output=True, text=True, timeout=600,
                )
                if result.stdout:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            print(f"  {line.strip()}")
                if result.returncode == 0:
                    print("[OK] 必要组件安装完成")
                    return (True, "")
                else:
                    err = result.stderr.strip() or result.stdout.strip() or '(无输出)'
                    print(f"[X] 必要组件安装失败 (exit {result.returncode}): {err}")
                    return (False, f"安装失败 (exit {result.returncode}): {err}{mirror_info}")
            except subprocess.TimeoutExpired:
                print("[X] 安装超时（超过 10 分钟），请检查网络后重试")
                return (False, f"下载超时（超过 10 分钟）{mirror_info}，请检查网络后重试")
            except Exception as ex:
                print(f"[X] 安装异常: {ex}")
                return (False, f"安装异常: {ex}{mirror_info}")
        else:
            # 开发模式：使用系统 Python
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
                    return (True, "")
                else:
                    err = result.stderr.strip() or result.stdout.strip() or '(无输出)'
                    print(f"[X] 安装失败 (exit {result.returncode}): {err}")
                    return (False, f"安装失败 (exit {result.returncode}): {err}{mirror_info}")
            except subprocess.TimeoutExpired:
                print("[X] 安装超时（超过 10 分钟），请检查网络后重试")
                return (False, f"下载超时（超过 10 分钟）{mirror_info}，请检查网络后重试")
            except Exception as ex:
                print(f"[X] 安装异常: {ex}")
                return (False, f"安装异常: {ex}{mirror_info}")


def _setup_logging(data_dir):
    """将 stdout/stderr 重定向到日志文件（无控制台窗口时仍需保留日志）"""
    log_path = os.path.join(data_dir, 'run.log')
    # 限制日志文件大小：超过 1MB 截断
    if os.path.isfile(log_path) and os.path.getsize(log_path) > 1 * 1024 * 1024:
        os.remove(log_path)
    log_file = open(log_path, 'a', encoding='utf-8', buffering=1)  # 行缓冲
    sys.stdout = log_file
    sys.stderr = log_file
    # Python 的 logging 也输出到同一文件
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
        # 打包模式：无控制台窗口，stdout/stderr → 日志文件
        log_path = _setup_logging(data_dir)

    print("=" * 60)
    print("  IEI Timer Faster V1.0.0")
    print("=" * 60)
    if is_frozen:
        print(f"[OK] 日志文件: {log_path}")
    print(f"[OK] 数据目录: {data_dir}")

    # 初始化内置缓存文件（仅节假日，不包含用户任务缓存）
    _seed_cache(bundle_dir, data_dir)

    # 确保 bundle_dir 在 sys.path 中以便导入 app
    if bundle_dir not in sys.path:
        sys.path.insert(0, bundle_dir)

    # 导入 Flask 应用
    from app import app

    # 切换到数据目录（app.py 中 cache/ 路径相对于 CWD）
    os.chdir(data_dir)

    # ---------- 免登录 API（绕开 app.py 的 _intercept_unauth_api）----------
    # app.py 的 before_request 会拦截所有 /api/*（除 login/logout），
    # 要求 get_client() != None。monkey-patch 在 PyInstaller 下不可靠。
    # 改用一个 before_request hook（插在最前面）直接返回 API 响应，
    # 短路后续所有 hook，确保免登录访问。

    def _public_api_credentials():
        from flask import request as _req
        if _req.method == 'POST':
            data = _req.get_json(silent=True) or {}
            u = (data.get('username') or '').strip()
            p = (data.get('password') or '').strip()
            if u and p:
                _save_credentials(data_dir, u, p)
                return app.response_class(
                    response=json.dumps({'success': True, 'message': '已保存'}),
                    status=200, mimetype='application/json')
            return app.response_class(
                response=json.dumps({'success': False, 'message': '缺少用户名或密码'}),
                status=200, mimetype='application/json')
        elif _req.method == 'DELETE':
            _delete_credentials(data_dir)
            return app.response_class(
                response=json.dumps({'success': True, 'message': '已清除'}),
                status=200, mimetype='application/json')
        else:  # GET
            username, password = _load_credentials(data_dir)
            if username:
                return app.response_class(
                    response=json.dumps({'success': True, 'username': username, 'password': password}),
                    status=200, mimetype='application/json')
            return app.response_class(
                response=json.dumps({'success': False}),
                status=200, mimetype='application/json')

    # 也注册为正常路由（通过 flask url 反向查找等场景需要）
    app.add_url_rule('/api/saved-credentials', 'api_saved_credentials',
                     _public_api_credentials, methods=['GET', 'POST', 'DELETE'])

    # ---------- 登录页注入：auto-fill + 自动保存 + CDN 本地化 ----------

    _CDN_MAP = {
        'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css':
            '/static/lib/bootstrap.min.css',
        'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css':
            '/static/lib/bootstrap-icons.css',
        'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js':
            '/static/lib/bootstrap.bundle.min.js',
    }

    @app.after_request
    def _rewrite_cdn_and_inject_creds(response):
        from flask import request as _req
        ct = response.content_type or ''
        if 'text/html' not in ct or response.status_code != 200:
            return response
        html = response.get_data(as_text=True)

        # 1) CDN → 本地 static/lib/
        for cdn_url, local_path in _CDN_MAP.items():
            html = html.replace(cdn_url, local_path)

        # 2) 页面注入脚本
        if _req.path == '/':
            # 登录页
            script = (
                '<script>'
                # 隐藏"密码以明文形式保存"（现在用 AES 加密了）
                'try{document.querySelector(".remember-hint").style.display="none"}catch(e){}'
                # 自动回填
                ';fetch("/api/saved-credentials").then(r=>r.json()).then(d=>{'
                'if(d.success){'
                'var u=document.getElementById("username");'
                'var p=document.getElementById("password");'
                'if(u&&p){u.value=d.username;p.value=d.password}'
                'document.getElementById("rememberMe").checked=true;'
                '}})'
                # 提交时保存
                ';document.getElementById("loginForm").addEventListener("submit",function(){'
                'var u=document.getElementById("username").value.trim();'
                'var p=document.getElementById("password").value.trim();'
                'if(u&&p){fetch("/api/saved-credentials",{method:"POST",keepalive:true,'
                'headers:{"Content-Type":"application/json"},'
                'body:JSON.stringify({username:u,password:p})})}'
                '})'
                # 清除按钮同时删文件
                ';document.getElementById("clearBtn").addEventListener("click",function(){'
                'fetch("/api/saved-credentials",{method:"DELETE"})'
                '})'
                '</script>'
            )
        elif _req.path == '/dashboard':
            # 主页面：确保"从RDM同步"按钮始终可见可点击
            script = (
                '<script>'
                'setInterval(function(){'
                'var b=document.getElementById("syncBtn");'
                'if(b){b.disabled=false;b.style.display=""}'
                '},300)'
                '</script>'
            )
        else:
            script = None

        if script:
            html = html.replace('</body>', script + '\n</body>')

        response.set_data(html)
        return response

    if is_frozen:
        # ============================================================
        # 打包模式：Flask 在后台线程 + pywebview 独立桌面窗口
        # ============================================================

        # 全局初始化状态（Chromium 下载期间显示加载页）
        _init_ready = [False]
        _init_stage = ["准备中..."]
        _init_error = [False]

        # INSPUR-52: 预打包 Chromium 浏览器，消除首次启动下载等待
        _prebuilt_ok, _prebuilt_copied = _copy_prebuilt_browsers(bundle_dir, data_dir)
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(data_dir, 'playwright-browsers')
        if _prebuilt_ok:
            if _prebuilt_copied:
                # 首次启动（刚复制完浏览器），验证可用性
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p:
                        p.chromium.launch(headless=True).close()
                    print("[OK] 预打包浏览器组件验证通过，跳过下载")
                except Exception as e:
                    print("[!] 预打包浏览器组件验证失败: %s，将尝试后台下载" % e)
                    # INSPUR-53: 输出诊断信息方便远程排查
                    _browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '(未设置)')
                    print("    PLAYWRIGHT_BROWSERS_PATH = %s" % _browsers_path)
                    if os.path.isdir(_browsers_path):
                        print("    目录内容: %s" % os.listdir(_browsers_path))
                    else:
                        print("    目录不存在")
                    _prebuilt_ok = False
            else:
                print("[OK] 浏览器组件已存在，跳过验证")
            if _prebuilt_ok:
                _init_ready[0] = True
                _init_stage[0] = "初始化完成"

        def _public_api_init_status():
            return app.response_class(
                response=json.dumps({
                    'ready': _init_ready[0],
                    'stage': _init_stage[0],
                    'error': _init_error[0],
                }),
                status=200, mimetype='application/json')

        app.add_url_rule('/api/init-status', 'api_init_status', _public_api_init_status)

        @app.route('/init')
        def _init_page():
            return '''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>正在启动...</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{display:flex;align-items:center;justify-content:center;height:100vh;
  font-family:"Microsoft YaHei",sans-serif;background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#e0e0e0}
.spinner{width:44px;height:44px;border:4px solid rgba(255,255,255,0.1);border-top:4px solid #4fc3f7;
  border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 24px}
@keyframes spin{to{transform:rotate(360deg)}}
h2{font-size:22px;font-weight:400;margin-bottom:12px;color:#fff}
.status{font-size:13px;color:#888;max-width:300px}.status.error{color:#f44336}
.dots::after{content:"";animation:dots 1.5s steps(4,end) infinite}
@keyframes dots{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}}
</style></head><body>
<div style="text-align:center">
<div class="spinner"></div>
<h2>IEI Timer Faster</h2><p style="color:#888;font-size:12px;margin-top:-8px">V1.0.0</p>
<p class="status" id="s">正在初始化<span class="dots"></span></p>
</div>
<script>
function check(){
fetch("/api/init-status").then(function(r){return r.json()}).then(function(d){
var s=document.getElementById("s");s.textContent=d.stage;
if(d.error){s.className="status error"}
if(d.ready){location.href="/"}else{setTimeout(check,1000)}
}).catch(function(){setTimeout(check,2000)})
}
check();
</script></body></html>'''

        # 未就绪时 / 重定向到 /init
        def _guard_init():
            from flask import request as _r, redirect as _rd
            # 免登录 API 直接放行（返回响应短路 _intercept_unauth_api）
            if _r.path == '/api/init-status':
                return _public_api_init_status()
            if _r.path == '/api/saved-credentials':
                return _public_api_credentials()
            if _r.path in ('/', '/dashboard') and not _init_ready[0]:
                return _rd('/init')
            return None
        app.before_request_funcs.setdefault(None, []).insert(0, _guard_init)

        # Chromium 安装（后台线程，更新状态让前端看到进度）
        def _install_chromium_bg():
            # INSPUR-52: 预打包浏览器已就绪则直接跳过
            if _init_ready[0]:
                return
            _init_stage[0] = "正在检查必要组件..."
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    b = p.chromium.launch(headless=True)
                    b.close()
                _init_stage[0] = "初始化完成"
                _init_ready[0] = True
                print("[OK] 必要组件已就绪")
                return
            except Exception as e:
                # INSPUR-53: 输出诊断信息方便远程排查
                _browsers_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '(未设置)')
                print("[!] 浏览器启动失败: %s" % e)
                print("    PLAYWRIGHT_BROWSERS_PATH = %s" % _browsers_path)
                if os.path.isdir(_browsers_path):
                    print("    目录内容: %s" % os.listdir(_browsers_path))
                else:
                    print("    目录不存在")
            _init_stage[0] = "首次运行，正在下载必要组件（约150MB，请耐心等待）..."
            success, error = _ensure_playwright_browsers(data_dir)
            if success:
                _init_stage[0] = "初始化完成"
                _init_ready[0] = True
            else:
                _init_stage[0] = error
                _init_error[0] = True

        threading.Thread(target=_install_chromium_bg, daemon=True).start()

        # 强制 WebView2 使用持久化数据目录
        webview_data = os.path.join(data_dir, 'webview-data')
        os.environ['WEBVIEW2_USER_DATA_FOLDER'] = webview_data

        print("[OK] 启动服务 http://127.0.0.1:5000 ...")

        flask_thread = threading.Thread(
            target=lambda: app.run(
                debug=False, host='127.0.0.1', port=5000,
                use_reloader=False,
            ),
            daemon=True,
        )
        flask_thread.start()

        # 等 Flask 真正就绪（轮询 /init，避免黑窗）
        print("[OK] 等待服务就绪...")
        import urllib.request as _ur
        for _ in range(40):
            try:
                _ur.urlopen('http://127.0.0.1:5000/init', timeout=0.5)
                break
            except Exception:
                time.sleep(0.25)

        try:
            import webview
            webview.create_window(
                'IEI Timer Faster',
                'http://127.0.0.1:5000',
                width=1280,
                height=860,
                min_size=(900, 600),
                resizable=True,
                text_select=True,
            )
            print("[OK] 桌面窗口已打开，关闭窗口即可退出程序")
            webview.start()
            print("[OK] 桌面窗口已关闭")
        except Exception as e:
            print(f"[X] 桌面窗口启动失败: {e}")
            print("    请手动访问 http://127.0.0.1:5000")
            # 阻塞主线程，等用户 Ctrl+C
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    else:
        # ============================================================
        # 开发模式：Flask 在主线程 + webbrowser 打开系统浏览器
        # debug=True 支持热重载，方便开发调试
        # ============================================================
        import webbrowser

        def _open_browser():
            time.sleep(2.0)
            webbrowser.open('http://127.0.0.1:5000')

        threading.Thread(target=_open_browser, daemon=True).start()

        print("[OK] 启动服务 http://127.0.0.1:5000 (debug 模式) ...")
        print("    浏览器将自动打开，如未打开请手动访问上述地址")
        print("    按 Ctrl+C 停止服务器")
        print()

        app.run(debug=True, host='127.0.0.1', port=5000)


if __name__ == '__main__':
    main()
