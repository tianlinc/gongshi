#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享启动器模块 — desktop/run.py 和 service_installer/service_launcher.py 的公共提取。

消除约 1300 行中 80%+ 的代码重复，同时保留差异化特性：
  - desktop/run.py:        固定端口 5000, 支持 CEF 后端 (INSPUR-70)
  - service_launcher.py:   端口自动递增 5000-5002, 仅 WebView2

使用:
    from _desktop_common import DesktopLauncher

    launcher = DesktopLauncher(port=5000, port_auto=False, enable_cef=True)
    launcher.run()
"""

import os
import sys
import shutil
import time
import socket
import threading
import json
import base64


# =========================================================================
# 公共工具函数
# =========================================================================

def _get_bundle_dir():
    """获取打包资源目录（项目根目录）。

    PyInstaller frozen: sys._MEIPASS
    开发模式: _desktop_common.py 所在目录（项目根目录）
    """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    # _desktop_common.py 在项目根目录，直接取 dirname(__file__) 即可
    return os.path.dirname(os.path.abspath(__file__))


def _get_data_dir():
    """获取用户数据目录，确保 cache/ 子目录存在。

    Windows: %APPDATA%/gongshi/
    macOS:   ~/Library/Application Support/gongshi/
    其他:    ~/gongshi/
    """
    if sys.platform == 'darwin':
        data_dir = os.path.join(
            os.path.expanduser('~'), 'Library', 'Application Support', 'gongshi')
    elif sys.platform == 'win32':
        appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
        data_dir = os.path.join(appdata, 'gongshi')
    else:
        data_dir = os.path.join(os.path.expanduser('~'), 'gongshi')
    os.makedirs(os.path.join(data_dir, 'cache'), exist_ok=True)
    return data_dir


def _seed_cache(bundle_dir, data_dir):
    """将打包内置的 cache 文件复制到用户数据目录。

    仅复制节假日缓存（holidays*.json），不复制用户任务缓存。
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


def _setup_logging(data_dir):
    """将 stdout/stderr 重定向到日志文件。

    无控制台窗口（console=False）时，日志是唯一的调试手段。
    文件超过 1MB 时自动截断。
    """
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


def _read_version():
    """读取 VERSION 文件。

    开发模式：项目根目录/VERSION
    frozen 模式：sys._MEIPASS/VERSION
    读取失败返回 fallback '0.0.0'。
    """
    version_path = os.path.join(_get_bundle_dir(), 'VERSION')
    try:
        with open(version_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return '0.0.0'


def _find_available_port(start=5000, max_tries=3):
    """找可用端口，依次尝试 start ~ start+max_tries-1。"""
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return None


# =========================================================================
# 凭证管理
# =========================================================================

_CRED_AES_KEY = b'gongshi_desk_202'


class CredentialManager:
    """AES-ECB 凭证加密存储。

    复用 app.py 的加密栈，密钥与 app.py 独立隔离。
    """

    @staticmethod
    def save(data_dir, username, password):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        path = os.path.join(data_dir, 'credentials.dat')
        payload = json.dumps({'u': username, 'p': password})
        cipher = AES.new(_CRED_AES_KEY, AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(payload.encode('utf-8'), AES.block_size))
        with open(path, 'wb') as f:
            f.write(base64.b64encode(encrypted))
        print(f"[OK] 凭证已加密保存 -> {path}")

    @staticmethod
    def load(data_dir):
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

    @staticmethod
    def delete(data_dir):
        path = os.path.join(data_dir, 'credentials.dat')
        if os.path.isfile(path):
            os.remove(path)
            print("[OK] 凭证已删除")


# =========================================================================
# 更新检查器
# =========================================================================

_update_checker = None


def get_update_checker():
    """获取 UpdateChecker 模块级单例。"""
    global _update_checker
    if _update_checker is None:
        _update_checker = UpdateChecker()
    return _update_checker


class UpdateChecker:
    """跨平台更新检查器。

    Windows:  GitHub Releases API → .exe 安装包
    macOS:    appcast.xml（Sparkle 协议）→ .dmg 安装包

    Thread-safe：下载状态用 threading.Lock 保护。
    超时 5s — 网络无响应时静默放弃，不阻塞主流程。
    """

    GITHUB_API = 'https://api.github.com/repos/tianlinc/gongshi/releases/latest'
    APPCASAT_URL = 'https://tianlinc.github.io/gongshi/appcast.xml'
    TIMEOUT = 5  # API 请求超时（秒）

    def __init__(self):
        self._lock = threading.Lock()
        self._last_check = None       # 最近一次 check_update 结果 dict 或 None（无更新/未检查）
        self._downloading = False
        self._progress_percent = 0
        self._downloaded = False
        self._file_path = None
        self._error = None

    # ---- 版本检查 ----

    def check_update(self, current_version):
        """检查是否有新版本。

        Windows: GitHub Releases API
        macOS:   appcast.xml（Sparkle 协议）

        Parameters
        ----------
        current_version : str
            当前版本号，如 "1.0.0"（不含 v 前缀）

        Returns
        -------
        dict or None
            有新版本时返回 {has_update, version, download_url, release_notes}
            无更新或网络错误时返回 None
        """
        if sys.platform == 'darwin':
            return self._check_mac_update(current_version)
        else:
            return self._check_windows_update(current_version)

    def _check_windows_update(self, current_version):
        """Windows 平台：从 GitHub Releases API 检查更新。"""
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.Request(
                self.GITHUB_API,
                headers={'User-Agent': 'gongshi-updater/1.0'}
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as _e:
            print(f"[!] 更新检查失败（网络异常）: {_e}")
            self._last_check = None
            return None

        tag = data.get('tag_name', '')
        remote_version = tag.lstrip('v')

        if not self._is_newer(remote_version, current_version):
            self._last_check = None
            return None

        # 找到当前平台的安装包
        download_url = None
        body = data.get('body', '')
        for asset in data.get('assets', []):
            name = asset.get('name', '')
            if sys.platform == 'win32' and name.lower().endswith('.exe'):
                download_url = asset.get('browser_download_url')
                break

        result = {
            'has_update': True,
            'version': remote_version,
            'download_url': download_url,
            'release_notes': body or '',
        }
        self._last_check = result
        return result

    def _check_mac_update(self, current_version):
        """macOS 平台：从 appcast.xml（Sparkle 协议）检查更新。"""
        import urllib.request
        import urllib.error
        import xml.etree.ElementTree as ET

        try:
            req = urllib.request.Request(
                self.APPCASAT_URL,
                headers={'User-Agent': 'gongshi-updater/1.0'}
            )
            with urllib.request.urlopen(req, timeout=self.TIMEOUT) as resp:
                xml_text = resp.read().decode('utf-8')
        except Exception as _e:
            print(f"[!] 更新检查失败（网络异常）: {_e}")
            self._last_check = None
            return None

        try:
            root = ET.fromstring(xml_text)
        except Exception as _e:
            print(f"[!] appcast.xml 解析失败: {_e}")
            self._last_check = None
            return None

        # 解析 Sparkle namespaced XML
        ns = {'sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle'}
        items = root.findall('.//channel/item')
        if not items:
            self._last_check = None
            return None

        first_item = items[0]
        enclosure = first_item.find('enclosure')
        if enclosure is None:
            self._last_check = None
            return None

        remote_version = (
            enclosure.get('{http://www.andymatuschak.org/xml-namespaces/sparkle}version') or
            ''
        )
        download_url = enclosure.get('url', '')
        title = first_item.findtext('title', '')
        description = first_item.findtext('description', '') or ''

        if not remote_version or not self._is_newer(remote_version, current_version):
            self._last_check = None
            return None

        result = {
            'has_update': True,
            'version': remote_version,
            'download_url': download_url,
            'release_notes': f'{title}\n{description}',
        }
        self._last_check = result
        return result

    def _is_newer(self, remote, current):
        """简单三段式版本号比较（a.b.c）。"""
        def _parse(v):
            try:
                return tuple(int(x) for x in str(v).split('.'))
            except (ValueError, TypeError):
                return (0, 0, 0)
        return _parse(remote) > _parse(current)

    # ---- 下载 ----

    def start_download(self, url, save_dir):
        """启动后台下载线程。

        Parameters
        ----------
        url : str
            安装包下载地址
        save_dir : str
            保存目录（如 %APPDATA%/gongshi/updates/）
        """
        self._reset_download_state()
        threading.Thread(
            target=self._do_download, args=(url, save_dir), daemon=True
        ).start()

    def _reset_download_state(self):
        with self._lock:
            self._downloading = True
            self._progress_percent = 0
            self._downloaded = False
            self._file_path = None
            self._error = None

    def _do_download(self, url, save_dir):
        """后台下载，更新进度状态。"""
        import urllib.request
        import urllib.error

        os.makedirs(save_dir, exist_ok=True)
        filename = url.rsplit('/', 1)[-1] or 'update.exe'
        filepath = os.path.join(save_dir, filename)

        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'gongshi-updater/1.0'}
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                total = int(resp.headers.get('Content-Length', 0))
                so_far = 0
                with open(filepath, 'wb') as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        so_far += len(chunk)
                        if total > 0:
                            pct = int(so_far * 100 / total)
                            with self._lock:
                                self._progress_percent = pct

            with self._lock:
                self._downloading = False
                self._downloaded = True
                self._file_path = filepath
                self._progress_percent = 100
            print(f"[OK] 更新包下载完成: {filepath}")

        except Exception as e:
            with self._lock:
                self._downloading = False
                self._downloaded = False
                self._error = str(e)
            print(f"[X] 更新包下载失败: {e}")

    # ---- 状态查询（线程安全） ----

    def get_status(self):
        """获取当前下载状态。"""
        with self._lock:
            return {
                'downloading': self._downloading,
                'progress_percent': self._progress_percent,
                'downloaded': self._downloaded,
                'error': self._error,
            }

    def get_file_path(self):
        """获取下载的安装包文件路径。"""
        with self._lock:
            return self._file_path

    def install_update(self):
        """安装已下载的更新包。

        Windows: subprocess 启动静默安装，然后退出当前进程
        macOS:   open 命令打开 DMG，弹出 Finder

        返回 (success: bool, message: str)
        """
        with self._lock:
            file_path = self._file_path
            downloaded = self._downloaded

        if not downloaded or not file_path or not os.path.isfile(file_path):
            return False, '安装包文件不存在'
        print(f"[OK] 安装模式: platform={sys.platform}, file={file_path}")  # noqa: W503

        if sys.platform == 'win32':
            return self._install_windows(file_path)
        elif sys.platform == 'darwin':
            return self._install_mac(file_path)
        else:
            return False, f'不支持的平台: {sys.platform}'

    @staticmethod
    def _get_windows_install_dir():
        """从注册表读取现有安装目录。

        Returns
        -------
        str or None
            安装目录路径，读取失败返回 None
        """
        try:
            import winreg
            appid = '{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}'
            for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    key = winreg.OpenKey(
                        root,
                        f'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{appid}_is1'
                    )
                    install_dir, _ = winreg.QueryValueEx(key, 'InstallLocation')
                    winreg.CloseKey(key)
                    if install_dir and os.path.isdir(install_dir):
                        return install_dir
                except OSError:
                    continue
        except Exception:
            pass
        return None

    @staticmethod
    def _install_windows(file_path):
        """Windows 平台：用 subprocess 启动 Inno Setup 静默安装。"""
        import subprocess

        # 尝试读取现有安装目录
        install_dir = UpdateChecker._get_windows_install_dir()

        cmd = [file_path, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART']
        if install_dir:
            cmd.append(f'/DIR={install_dir}')
            print(f"[OK] 安装目录: {install_dir}")
        else:
            print("[!] 未找到现有安装目录，使用默认目录")

        try:
            print(f"[OK] 静默安装命令: {' '.join(cmd)}")
            subprocess.Popen(cmd, shell=True)
        except Exception as e:
            return False, f'启动安装失败: {e}'

        # 退出当前进程，让安装程序替换文件
        print("[OK] 更新安装已启动，退出当前进程")
        os._exit(0)

    @staticmethod
    def _install_mac(file_path):
        """macOS 平台：打开 DMG 文件。"""
        import subprocess

        try:
            subprocess.run(['open', file_path], check=True)
            print(f"[OK] 已打开 DMG: {file_path}")
            return True, '已打开 DMG 文件，请在 Finder 中拖入应用程序'
        except Exception as e:
            return False, f'打开 DMG 失败: {e}'


# =========================================================================
# DesktopLauncher — 主启动器类
# =========================================================================

class DesktopLauncher:
    """Flask + pywebview 桌面启动器。

    统一 desktop/run.py 和 service_installer/service_launcher.py 的启动逻辑，
    通过构造参数区分差异化行为。

    Parameters
    ----------
    port : int
        起始端口号，默认 5000
    port_auto : bool
        True=端口冲突时自动递增（service_launcher.py 特性）
        False=固定端口（run.py 特性）
    enable_cef : bool
        True=支持 GONGSHI_GUI_BACKEND=cef 环境变量（run.py INSPUR-70 特性）
        False=仅使用 WebView2
    """

    # CDN → 本地映射（两个启动器完全一致）
    _CDN_MAP = {
        'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css':
            '/static/lib/bootstrap.min.css',
        'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css':
            '/static/lib/bootstrap-icons.css',
        'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js':
            '/static/lib/bootstrap.bundle.min.js',
    }

    # 初始化加载页 HTML（两个启动器完全一致）
    _INIT_HTML = '''<!DOCTYPE html>
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
<h2>IEI Timer Faster</h2><p style="color:#888;font-size:12px;margin-top:-8px">V{version}</p>
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

    def __init__(self, port=5000, port_auto=False, enable_cef=False):
        self._port = port
        self._port_auto = port_auto
        self._enable_cef = enable_cef

    # =================================================================
    # 统一的启动入口
    # =================================================================

    def run(self):
        """完整启动流程：初始化 → Flask 路由注册 → 桌面窗口。"""
        is_frozen = getattr(sys, 'frozen', False)
        bundle_dir = _get_bundle_dir()
        data_dir = _get_data_dir()
        cred = CredentialManager

        if is_frozen:
            log_path = _setup_logging(data_dir)

        # 横幅
        _ver = _read_version()
        print("=" * 60)
        print(f"  IEI Timer Faster V{_ver}")
        print("=" * 60)
        if is_frozen:
            print(f"[OK] 日志文件: {log_path}")
        print(f"[OK] 数据目录: {data_dir}")

        # 初始化内置缓存文件
        _seed_cache(bundle_dir, data_dir)

        # 确保项目根目录在 sys.path 中（dev 模式需要，frozen 由 PyInstaller 处理）
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)

        from app import app

        # 切换到数据目录（app.py 中 cache/ 路径相对于 CWD）
        os.chdir(data_dir)

        # ---- 注册 Flask 路由和钩子（所有模式都需要） ----

        # 凭证 API（闭包捕获 data_dir/cred/app，用于路由和 before_request 短路）
        def _api_credentials():
            from flask import request as _req
            if _req.method == 'POST':
                d = _req.get_json(silent=True) or {}
                u = (d.get('username') or '').strip()
                p = (d.get('password') or '').strip()
                if u and p:
                    cred.save(data_dir, u, p)
                    return app.response_class(
                        response=json.dumps({'success': True, 'message': '已保存'}),
                        status=200, mimetype='application/json')
                return app.response_class(
                    response=json.dumps({'success': False, 'message': '缺少用户名或密码'}),
                    status=200, mimetype='application/json')
            elif _req.method == 'DELETE':
                cred.delete(data_dir)
                return app.response_class(
                    response=json.dumps({'success': True, 'message': '已清除'}),
                    status=200, mimetype='application/json')
            else:  # GET
                username, password = cred.load(data_dir)
                if username:
                    return app.response_class(
                        response=json.dumps({'success': True, 'username': username, 'password': password}),
                        status=200, mimetype='application/json')
                return app.response_class(
                    response=json.dumps({'success': False}),
                    status=200, mimetype='application/json')

        app.add_url_rule('/api/saved-credentials', 'api_saved_credentials',
                         _api_credentials, methods=['GET', 'POST', 'DELETE'])

        # CDN 改写 + 页面注入钩子
        self._register_cdn_rewrite_hook(app)

        if is_frozen:
            self._run_frozen(app, data_dir, _api_credentials)
        else:
            self._run_dev(app)

    # =================================================================
    # Flask 钩子注册
    # =================================================================

    def _register_cdn_rewrite_hook(self, app):
        """注册 after_request 钩子：CDN 改写 + 凭证回填 + 同步按钮启用。"""
        cdn_map = self._CDN_MAP

        @app.after_request
        def rewrite(response):
            from flask import request as _req
            ct = response.content_type or ''
            if 'text/html' not in ct or response.status_code != 200:
                return response
            html = response.get_data(as_text=True)

            # 1) CDN → 本地 static/lib/
            for cdn_url, local_path in cdn_map.items():
                html = html.replace(cdn_url, local_path)

            # 2) 页面注入
            if _req.path == '/':
                # 登录页：凭证回填 + 自动保存
                script = (
                    '<script>'
                    'try{document.querySelector(".remember-hint").style.display="none"}catch(e){}'
                    ';fetch("/api/saved-credentials").then(r=>r.json()).then(d=>{'
                    'if(d.success){'
                    'var u=document.getElementById("username");'
                    'var p=document.getElementById("password");'
                    'if(u&&p){u.value=d.username;p.value=d.password}'
                    'document.getElementById("rememberMe").checked=true;'
                    '}})'
                    ';document.getElementById("loginForm").addEventListener("submit",function(){'
                    'var u=document.getElementById("username").value.trim();'
                    'var p=document.getElementById("password").value.trim();'
                    'if(u&&p){fetch("/api/saved-credentials",{method:"POST",keepalive:true,'
                    'headers:{"Content-Type":"application/json"},'
                    'body:JSON.stringify({username:u,password:p})})}'
                    '})'
                    ';document.getElementById("clearBtn").addEventListener("click",function(){'
                    'fetch("/api/saved-credentials",{method:"DELETE"})'
                    '})'
                    '</script>'
                )
            elif _req.path == '/dashboard':
                # 主页面：同步按钮强制启用
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

    # =================================================================
    # 运行模式
    # =================================================================

    def _run_frozen(self, app, data_dir, api_credentials):
        """打包模式：Flask 后台线程 + pywebview 桌面窗口。"""

        # 初始化状态（mutable closure so guard_init 能看到变化）
        _init_ready = [True]
        _init_stage = ["初始化完成"]
        _init_error = [False]

        def _api_init_status():
            return app.response_class(
                response=json.dumps({
                    'ready': _init_ready[0],
                    'stage': _init_stage[0],
                    'error': _init_error[0],
                }),
                status=200, mimetype='application/json')

        app.add_url_rule('/api/init-status', 'api_init_status', _api_init_status)

        @app.route('/init')
        def _init_page():
            return self._INIT_HTML.replace('{version}', _read_version())

        # Guard: 未就绪时重定向到 /init，并短路免登录 API 的鉴权检查
        def _guard_init():
            from flask import request as _r, redirect as _rd
            if _r.path == '/api/init-status':
                return _api_init_status()
            if _r.path == '/api/saved-credentials':
                # 短路 _intercept_unauth_api 鉴权，直接返回凭证响应
                return api_credentials()
            if _r.path in ('/', '/dashboard') and not _init_ready[0]:
                return _rd('/init')
            return None

        app.before_request_funcs.setdefault(None, []).insert(0, _guard_init)

        # ---- 端口选择 ----
        if self._port_auto:
            port = _find_available_port(self._port, 3)
            if port is None:
                print("[X] 端口 %d/%d/%d 均被占用，请关闭占用程序后重试" %
                      (self._port, self._port + 1, self._port + 2))
                sys.exit(1)
            if port != self._port:
                print(f"[!] {self._port} 端口被占用，使用 {port}")
        else:
            port = self._port

        url = f"http://127.0.0.1:{port}"

        # ---- GUI 后端选择 ----
        gui_backend = 'webview2'
        cef_available = False
        cef_cache_dir = None

        if sys.platform == 'darwin':
            # macOS: 系统原生 Cocoa/WebKit 后端（WKWebView）
            gui_backend = 'cocoa'
            print("[OK] GUI 后端: Cocoa/WebKit (macOS 原生)")
        else:
            # Windows: 默认 WebView2 + CEF 可选
            if self._enable_cef:
                # INSPUR-70: CEF 自包含 Chromium 后端（仅 run.py）
                gui_backend = os.environ.get('GONGSHI_GUI_BACKEND', 'webview2').lower()
                if gui_backend == 'cef':
                    try:
                        import cefpython3  # noqa: F401
                        cef_available = True
                    except Exception as _e:
                        cef_available = False
                        print("[!] cefpython3 不可用 (%s)，回退到 WebView2" % _e)
                        gui_backend = 'webview2'

            if gui_backend == 'cef' and cef_available:
                cef_cache_dir = os.path.join(data_dir, 'cef-data')
                os.makedirs(cef_cache_dir, exist_ok=True)
                print("[OK] GUI 后端: CEF (内置 Chromium，缓存: %s)" % cef_cache_dir)
            else:
                webview_data = os.path.join(data_dir, 'webview-data')
                os.environ['WEBVIEW2_USER_DATA_FOLDER'] = webview_data
                print("[OK] GUI 后端: WebView2 (数据目录: %s)" % webview_data)

        print("[OK] 启动服务 %s ..." % url)

        # ---- Flask 后台线程 ----
        flask_thread = threading.Thread(
            target=lambda: app.run(
                debug=False, host='127.0.0.1', port=port,
                use_reloader=False,
            ),
            daemon=True,
        )
        flask_thread.start()

        # ---- 等待 Flask 就绪 ----
        print("[OK] 等待服务就绪...")
        import urllib.request as _ur
        for _ in range(40):
            try:
                _ur.urlopen(url + '/init', timeout=0.5)
                break
            except Exception:
                time.sleep(0.25)

        # ---- 后台更新检查（异步，不阻塞主流程）----
        def _check_for_update():
            time.sleep(2)  # 启动后延迟 2-3 秒，等 UI 渲染
            checker = get_update_checker()
            result = checker.check_update(_read_version())
            if result:
                print(f"[OK] 发现新版本 V{result['version']}")
            else:
                print("[OK] 已是最新版本")

        threading.Thread(target=_check_for_update, daemon=True).start()

        # ---- pywebview 桌面窗口 ----
        try:
            import webview
            webview.create_window(
                'IEI Timer Faster',
                url,
                width=1280,
                height=860,
                min_size=(900, 600),
                resizable=True,
                text_select=True,
            )
            print("[OK] 桌面窗口已打开，关闭窗口即可退出程序")

            if gui_backend == 'cef' and cef_available:
                webview.start(
                    gui='cef',
                    private_mode=False,
                    storage_path=cef_cache_dir,
                )
            else:
                webview.start()

            print("[OK] 桌面窗口已关闭")
        except Exception as e:
            print(f"[X] 桌面窗口启动失败: {e}")
            print("    请手动访问 %s" % url)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    def _run_dev(self, app):
        """开发模式：Flask 主线程 + webbrowser 打开系统浏览器。

        debug=True 支持热重载，方便开发调试。
        """
        import webbrowser

        if self._port_auto:
            port = _find_available_port(self._port, 3)
            if port is None:
                print("[X] 端口 %d/%d/%d 均被占用，请关闭占用程序后重试" %
                      (self._port, self._port + 1, self._port + 2))
                return
            if port != self._port:
                print(f"[!] {self._port} 端口被占用，使用 {port}")
        else:
            port = self._port

        url = f"http://127.0.0.1:{port}"

        def _open_browser():
            time.sleep(2.0)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

        print("[OK] 启动服务 %s (debug 模式) ..." % url)
        print("    浏览器将自动打开，如未打开请手动访问上述地址")
        print("    按 Ctrl+C 停止服务器")
        print()

        app.run(debug=True, host='127.0.0.1', port=port)
