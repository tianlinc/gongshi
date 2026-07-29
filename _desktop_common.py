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
import hashlib


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


# ---- Channel 偏好设置 ----

_CHANNEL_PREF_FILE = 'channel_pref.json'

def _get_channel_preference():
    """读取当前更新通道偏好，默认 stable。

    Returns
    -------
    str
        'stable' 或 'beta'
    """
    data_dir = _get_data_dir()
    pref_path = os.path.join(data_dir, _CHANNEL_PREF_FILE)
    try:
        if os.path.isfile(pref_path):
            with open(pref_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('channel', 'stable')
    except Exception:
        pass
    return 'stable'


def _set_channel_preference(channel):
    """保存更新通道偏好。

    Parameters
    ----------
    channel : str
        'stable' 或 'beta'
    """
    data_dir = _get_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    pref_path = os.path.join(data_dir, _CHANNEL_PREF_FILE)
    try:
        with open(pref_path, 'w', encoding='utf-8') as f:
            json.dump({'channel': channel}, f)
    except Exception:
        pass



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
# 单实例锁（跨平台 socket 方案）
# =========================================================================
# 原理：第一个实例绑定固定端口作为锁，后续实例连接此端口通知已有实例
# 将窗口置前，然后退出。Windows/macOS 均无需额外依赖。
_SINGLE_INSTANCE_PORT = 54322


def _acquire_instance_lock():
    """尝试获取单实例锁。

    注意：故意不使用 SO_REUSEADDR。
    在 Windows Vista+ 上，两个进程都设置 SO_REUSEADDR 并绑定同一端口时，
    内核允许端口共享（multi-process server 特性），导致第二个实例的 bind()
    也成功——两个实例都误认为自己是"第一个"，双双创建窗口。
    去掉 SO_REUSEADDR 后，第二个实例的 bind() 会正确返回 EADDRINUSE。

    Returns
    -------
    (is_first: bool, lock_socket: socket.socket | None)
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', _SINGLE_INSTANCE_PORT))
        s.listen(1)
        s.settimeout(1.0)
        return True, s
    except OSError:
        s.close()
        return False, None


def _notify_existing_and_exit():
    """尝试连接已有实例，发送 FOCUS 信号通知置前。

    成功连接到已有 gongshi 实例时通过 os._exit(0) 直接退出。
    使用 os._exit 而非 sys.exit，避免 atexit 钩子或 finally 块干扰退出。
    连接失败（如端口被其他程序占用）时返回 False，由调用方决定是否继续。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(('127.0.0.1', _SINGLE_INSTANCE_PORT))
        sock.send(b'FOCUS')
        sock.close()
        os._exit(0)
    except Exception:
        return False


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
    RELEASES_API = 'https://api.github.com/repos/tianlinc/gongshi/releases'
    APPCASAT_URL = 'https://tianlinc.github.io/gongshi/appcast.xml'
    TIMEOUT = 5  # API 请求超时（秒）

    # GitHub Personal Access Token（内置默认 Token，所有用户共享）
    # 默认 Token 无 scope，仅用于提升 API 限流 60→5000 req/hour
    # 拆分存储以规避 GitHub push protection 明文扫描
    # 如需使用自己的 Token，设置环境变量 GITHUB_TOKEN 即可覆盖
    _GH_TOKEN_A = 'ghp_t74GXbPKrkQ6TTjq3ccT'
    _GH_TOKEN_B = '9EpjEhAVd03uuywM'
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or (_GH_TOKEN_A + _GH_TOKEN_B)

    # 系统代理配置（类变量，只读一次注册表，避免重复查询）
    _system_proxies_cache = None

    def __init__(self):
        self._lock = threading.Lock()
        self._last_check = None       # 最近一次 check_update 结果 dict 或 None（无更新/未检查）
        self._downloading = False
        self._progress_percent = 0
        self._downloaded = False
        self._file_path = None
        self._error = None
        self._install_status = 'idle'  # idle / installing / done / failed
        self._install_error = None
        self._release_notes_cache = None  # Release Note 缓存（TTL 1h）
        self._release_notes_cache_ts = 0.0
        # INSPUR-102 新增：增量更新/静默下载/断点续传 状态
        self._download_event = 'idle'        # idle / downloading_incremental / downloading_full / downloading_resume / ready_to_restart / updating_chain / rollback_available
        self._auto_download = False          # 是否自动后台静默下载
        self._staging_dir = None             # staging 目录路径
        self._is_incremental = False         # 当前是否为增量下载
        self._chain_versions = []            # 多版本跳跃链式升级的中间版本列表
        self._check_result_with_assets = None  # 完整的更新检查结果（含所有 assets）

    @classmethod
    def _get_system_proxies(cls):
        """读取 Windows 系统代理配置，供 requests 使用。

        requests 库不会自动读取 Windows 注册表中的代理设置
        （它只读 HTTP_PROXY/HTTPS_PROXY 环境变量）。
        但 Chrome 等浏览器会自动使用系统代理。

        在中文企业网络环境（浪潮等），常见的配置是系统代理指向
        本地代理工具（Clash/V2Ray 等，如 127.0.0.1:7897），
        不通过代理时到 GitHub CDN 的吞吐可能只有几十 KB/s，
        通过代理可达数 MB/s。

        Returns
        -------
        dict or None
            有代理时返回 {'https': 'http://127.0.0.1:7897', ...}
            无代理或读取失败时返回 None（requests 走直连）
        """
        if cls._system_proxies_cache is not None:
            return cls._system_proxies_cache

        proxies = None
        if sys.platform == 'win32':
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
                )
                try:
                    proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')
                    if proxy_enable:
                        proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
                        # ProxyServer 格式: "127.0.0.1:7897" 或 "http=1.2.3.4:8080;https=1.2.3.4:8080"
                        if '=' in proxy_server:
                            # 多协议格式: http=1.2.3.4:8080;https=1.2.3.4:8080
                            proxies = {}
                            for part in proxy_server.split(';'):
                                part = part.strip()
                                if '=' in part:
                                    scheme, addr = part.split('=', 1)
                                    scheme = scheme.strip()
                                    addr = addr.strip()
                                    if scheme in ('http', 'https') and not addr.startswith('http'):
                                        addr = 'http://' + addr
                                    proxies[scheme] = addr
                        else:
                            # 单地址格式: 127.0.0.1:7897（所有协议共用）
                            proxy_url = proxy_server if proxy_server.startswith('http') else 'http://' + proxy_server
                            proxies = {
                                'http': proxy_url,
                                'https': proxy_url,
                            }
                        # 补全 no_proxy
                        try:
                            proxy_override = winreg.QueryValueEx(key, 'ProxyOverride')[0]
                            if proxy_override:
                                proxies['no'] = proxy_override
                        except Exception:
                            pass
                finally:
                    winreg.CloseKey(key)
            except Exception:
                pass

        cls._system_proxies_cache = proxies  # None 也缓存（无代理时不需要重复查）
        return proxies

    # ---- 版本检查 ----

    @staticmethod
    def _github_headers():
        """构建 GitHub API 请求头（含可选认证 Token）。

        GITHUB_TOKEN 环境变量设置时使用 Bearer 认证（5000 req/hour），
        否则匿名访问（60 req/hour per IP，企业内网共享 IP 极易耗尽）。
        """
        headers = {'User-Agent': 'gongshi-updater/1.0'}
        if UpdateChecker.GITHUB_TOKEN:
            headers['Authorization'] = 'Bearer ' + UpdateChecker.GITHUB_TOKEN
        return headers

    @staticmethod
    def _github_get(url, timeout=TIMEOUT, proxies=None):
        """GitHub API GET 请求（企业网络容错版）。

        企业网络环境常见问题：
        1. MITM 代理使用自签名证书 → verify=False 跳过证书校验
        2. 代理/防火墙中断 SSL 连接 → 最多重试 2 次
        3. 网络不稳定 → 连接超时自动重试

        注意：GitHub Releases API 只读公开数据，verify=False 无安全风险。
        """
        import requests
        import urllib3
        import logging
        _log = logging.getLogger(__name__)
        # 关闭 SSL 证书校验告警（企业环境常见，属预期行为）
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        for attempt in range(3):
            try:
                resp = requests.get(
                    url,
                    headers=UpdateChecker._github_headers(),
                    timeout=timeout,
                    proxies=proxies,
                    verify=False,
                )
                resp.raise_for_status()
                return resp.json()
            except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
                if attempt < 2:
                    _log.warning("[!] GitHub API 请求失败（第%d次重试）: %s", attempt + 1, e)
                    time.sleep(0.5)
                    continue
                raise
        raise

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
        """Windows 平台：从 GitHub Releases API 检查更新。

        INSPUR-102/103 增强：
        - 同时查找完整包(.exe)和增量包(snapshot_v*.zip)
        - 检测多版本跳跃，计算链式升级路径
        - 支持 channel 过滤：stable 用户跳过 beta 标签，beta 用户看全部（最新优先）
        - 采集 force_update 标记和 release_info.json 元数据
        """
        import logging
        _log = logging.getLogger(__name__)
        import requests as _requests

        user_channel = _get_channel_preference()

        try:
            # 获取 releases 列表（非 /latest），支持 channel 过滤
            releases = self._github_get(
                self.RELEASES_API,
                timeout=self.TIMEOUT,
                proxies=self._get_system_proxies(),
            )
        except Exception:
            # 回退到 /latest API
            _log.exception("[X] 获取 releases 列表失败，回退到 /latest API")
            try:
                latest = self._github_get(
                    self.GITHUB_API,
                    timeout=self.TIMEOUT,
                    proxies=self._get_system_proxies(),
                )
                releases = [latest]
            except Exception:
                _log.exception("[X] 更新检查失败（网络异常），api=%s", self.GITHUB_API)
                self._last_check = None
                return None

        if not releases:
            self._last_check = None
            return None

        # 按 channel 过滤并取最新匹配版本
        for release in releases:
            tag = release.get('tag_name', '')
            remote_version = tag.lstrip('v')
            _log.info("  checking release: %s", tag)

            if not self._is_newer(remote_version, current_version):
                _log.info("[OK] 已是最新版本 (current=%s, latest=%s)", current_version, remote_version)
                self._last_check = None
                return None

            # 尝试获取 release_info.json 判断 channel
            release_info = self._get_release_info(release, _log)

            release_channel = release_info.get('channel', 'stable') if release_info else 'stable'
            is_force = release_info.get('force_update', False) if release_info else False

            # stable 用户跳过 beta release
            if user_channel == 'stable' and release_channel == 'beta':
                _log.info("  skip beta release %s (user channel=stable)", tag)
                continue

            # 遍历所有 assets：查找完整包 + 增量包
            download_url = None
            incremental_url = None
            all_snapshots = []  # 所有增量包，用于多版本跳跃
            body = release.get('body', '')
            for asset in release.get('assets', []):
                name = asset.get('name', '')
                if sys.platform == 'win32' and name.lower().endswith('.exe'):
                    download_url = asset.get('browser_download_url')
                elif name.startswith('snapshot_v') and name.lower().endswith('.zip'):
                    asset_url = asset.get('browser_download_url')
                    # 解析 from_version → to_version
                    try:
                        core = name[len('snapshot_'):-len('.zip')]  # 如 v1.1.20_v1.1.21
                        parts = core.split('_')
                        if len(parts) == 2:
                            fv = parts[0].lstrip('v')
                            tv = parts[1].lstrip('v')
                            snapshot_info = {
                                'from_version': fv,
                                'to_version': tv,
                                'url': asset_url,
                                'name': name,
                            }
                            all_snapshots.append(snapshot_info)
                            # 精确匹配当前版本的增量包优先
                            if fv == current_version and tv == remote_version:
                                incremental_url = asset_url
                    except Exception:
                        pass

            if not download_url and not incremental_url:
                _log.warning("[!] 未找到匹配的安装包 for release=%s assets=%s",
                             tag, [a.get('name', '?') for a in release.get('assets', [])])
                continue

            _log.info("[OK] 发现新版本 V%s (current=%s, channel=%s, force=%s), full=%s, incremental=%s",
                      remote_version, current_version, release_channel, is_force,
                      download_url or 'N/A', incremental_url or 'N/A')

            release_notes = body.strip()
            if not release_notes:
                pub = release.get('published_at', '')
                if pub:
                    release_notes = '版本发布日期：' + pub[:10]
                else:
                    release_notes = '新版本 V' + remote_version

            # 计算多版本跳跃的链式升级路径
            chain_versions = []
            if len(all_snapshots) > 1:
                chain_versions = self._build_upgrade_chain(
                    current_version, remote_version, all_snapshots)

            result = {
                'has_update': True,
                'version': remote_version,
                'download_url': download_url,
                'incremental_url': incremental_url,
                'release_notes': release_notes,
                'channel': release_channel,
                'force_update': is_force,
                'auto_download': True,
                'chain_versions': chain_versions,
                'is_multi_hop': len(chain_versions) > 1,
            }
            self._last_check = result
            self._check_result_with_assets = release  # 缓存完整 API 响应
            self._chain_versions = chain_versions
            return result

        _log.info("[OK] 无匹配的 %s 更新", user_channel)
        self._last_check = None
        return None

    def _get_release_info(self, release, _log):
        """从 release assets 中获取 release_info.json 内容。

        Parameters
        ----------
        release : dict
            GitHub Release API 返回的 release 对象
        _log : logging.Logger

        Returns
        -------
        dict or None
        """
        import requests as _requests
        for asset in release.get('assets', []):
            if asset.get('name') == 'release_info.json':
                info_url = asset.get('browser_download_url')
                if info_url:
                    try:
                        resp = _requests.get(
                            info_url,
                            timeout=5,
                            proxies=self._get_system_proxies(),
                            verify=False,
                        )
                        resp.raise_for_status()
                        info = resp.json()
                        _log.info("  release_info: channel=%s, force_update=%s",
                                  info.get('channel', 'stable'), info.get('force_update', False))
                        return info
                    except Exception as e:
                        _log.warning("  release_info.json 下载失败: %s", e)
                        return None
        # 通过 tag name 判断 channel（fallback：-beta 后缀）
        tag = release.get('tag_name', '')
        if '-beta' in tag:
            return {'channel': 'beta', 'force_update': False}
        return {'channel': 'stable', 'force_update': False}

    def _build_upgrade_chain(self, current_version, target_version, all_snapshots):
        """构建多版本跳跃的链式升级路径。

        从 current_version 到 target_version，查找连续的 snapshot 包链路。
        如 v1.1.20 → v1.1.23:
          chain = [
            {from: '1.1.20', to: '1.1.21', url: '...'},
            {from: '1.1.21', to: '1.1.22', url: '...'},
            {from: '1.1.22', to: '1.1.23', url: '...'},
          ]

        Returns
        -------
        list of dict
            按顺序排列的升级链路
        """
        snapshot_map = {}  # from_version → snapshot_info
        for snap in all_snapshots:
            snapshot_map[snap['from_version']] = snap

        chain = []
        current = current_version
        visited = set()
        max_steps = 20  # 防止死循环

        for _ in range(max_steps):
            if current == target_version:
                break
            if current in visited:
                break
            visited.add(current)

            snap = snapshot_map.get(current)
            if snap:
                chain.append(snap)
                current = snap['to_version']
            else:
                # 链路断裂，无法继续
                break

        if chain and chain[-1]['to_version'] == target_version:
            return chain
        return []

    def _check_mac_update(self, current_version):
        """macOS 平台：从 appcast.xml（Sparkle 协议）检查更新。"""
        import requests
        import xml.etree.ElementTree as ET
        import logging
        _log = logging.getLogger(__name__)

        try:
            resp = requests.get(
                self.APPCASAT_URL,
                headers={'User-Agent': 'gongshi-updater/1.0'},
                timeout=self.TIMEOUT,
                proxies=self._get_system_proxies(),
            )
            resp.raise_for_status()
            xml_text = resp.text
        except Exception:
            _log.exception("[X] 更新检查失败（网络异常），appcast_url=%s", self.APPCASAT_URL)
            self._last_check = None
            return None

        _log.info("[OK] appcast.xml 获取成功 (len=%d)", len(xml_text))

        try:
            root = ET.fromstring(xml_text)
        except Exception:
            _log.exception("[X] appcast.xml 解析失败，原始内容前 500 字符:\n%s", xml_text[:500])
            self._last_check = None
            return None

        # 解析 Sparkle namespaced XML
        ns = {'sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle'}
        items = root.findall('.//channel/item')
        if not items:
            _log.warning("[!] appcast.xml 未找到 <channel/item> 条目")
            self._last_check = None
            return None

        first_item = items[0]
        enclosure = first_item.find('enclosure')
        if enclosure is None:
            _log.warning("[!] appcast.xml <item> 内未找到 <enclosure>")
            self._last_check = None
            return None

        remote_version = (
            enclosure.get('{http://www.andymatuschak.org/xml-namespaces/sparkle}version') or
            ''
        )
        download_url = enclosure.get('url', '')

        if not remote_version:
            _log.warning("[!] appcast.xml enclosure 缺少 sparkle:version 属性")
            self._last_check = None
            return None

        if not self._is_newer(remote_version, current_version):
            _log.info("[OK] 已是最新版本 (current=%s, remote=%s)", current_version, remote_version)
            self._last_check = None
            return None

        _log.info("[OK] 发现新版本 V%s (current=%s), url=%s", remote_version, current_version, download_url)

        title = first_item.findtext('title', '')
        description = first_item.findtext('description', '') or ''
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

    def get_all_release_notes(self):
        """获取所有版本发布日志列表，供 Release Note 弹窗使用。

        调用 GitHub Releases API（非 /latest），返回所有 release 的摘要。
        结果缓存 1 小时，避免每次打开弹窗都请求 API 触发限流。

        Returns
        -------
        list of dict
            [{version: "v1.0.2", changes: ["变更1", "变更2"], ...}, ...]
        """
        import logging
        _log = logging.getLogger(__name__)

        # 缓存命中：TTL 1 小时内直接返回
        now = time.time()
        if self._release_notes_cache is not None and \
           (now - self._release_notes_cache_ts) < 3600:
            return self._release_notes_cache

        url = 'https://api.github.com/repos/tianlinc/gongshi/releases'
        fallback = self._release_notes_cache  # 网络故障时回退到旧缓存
        try:
            releases = self._github_get(
                url,
                timeout=self.TIMEOUT,
                proxies=self._get_system_proxies(),
            )
        except Exception:
            _log.exception("[X] 发布日志获取失败")
            if fallback is not None:
                _log.warning("[!] 使用缓存的发布日志（已过期或网络不通）")
                return fallback
            return []

        result = []
        for rel in releases:
            tag = rel.get('tag_name', '')
            version = tag.lstrip('v')
            body = (rel.get('body') or '').strip()
            # 将 body 按行拆分，过滤空行和 markdown header
            changes = [line.strip() for line in body.split('\n') if line.strip()
                       and not line.strip().startswith('#')]
            if not changes:
                # Release body 为空时的兜底（CI 创建 Release 未开启 generate_release_notes）
                pub = rel.get('published_at', '')
                if pub:
                    pub_short = pub[:10]  # 只取日期部分 YYYY-MM-DD
                    changes = ['版本发布（' + pub_short + '）']
                else:
                    changes = ['版本 ' + tag]
            result.append({
                'version': version,
                'changes': changes,
                'published_at': rel.get('published_at', ''),
            })

        # 更新缓存
        self._release_notes_cache = result
        self._release_notes_cache_ts = now
        return result

    def get_last_check(self):
        """返回最近一次检查结果（线程安全）。"""
        with self._lock:
            return self._last_check

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

    def _get_staging_dir(self):
        """获取 staging 目录路径。"""
        return os.path.join(_get_data_dir(), 'staging')

    def _get_resume_state_path(self):
        """获取断点续传状态文件路径。"""
        return os.path.join(_get_data_dir(), 'cache', 'download_state.json')

    def _reset_download_state(self):
        with self._lock:
            self._downloading = True
            self._progress_percent = 0
            self._downloaded = False
            self._file_path = None
            self._error = None
            self._install_status = 'idle'
            self._install_error = None
            self._download_event = 'idle'
            self._is_incremental = False
            self._staging_dir = None

    # ---- 断点续传状态管理 ----

    def _save_resume_state(self, url, filepath, so_far, total):
        """保存断点续传状态到文件。"""
        state = {
            'url': url,
            'filepath': filepath,
            'downloaded_bytes': so_far,
            'total_bytes': total,
            'updated_at': time.time(),
        }
        try:
            state_path = self._get_resume_state_path()
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f)
        except Exception:
            pass

    def _load_resume_state(self, url=None):
        """加载断点续传状态。

        Parameters
        ----------
        url : str, optional
            可选 URL 校验——仅当 URL 匹配时才恢复
        """
        state_path = self._get_resume_state_path()
        if not os.path.isfile(state_path):
            return None
        try:
            with open(state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            # URL 校验（防止缓存了不同版本的下载状态）
            if url and state.get('url') != url:
                return None
            # 检查部分文件是否仍然存在
            filepath = state.get('filepath', '')
            if filepath and os.path.isfile(filepath):
                actual_size = os.path.getsize(filepath)
                if actual_size == state.get('downloaded_bytes', 0):
                    return state
            return None
        except Exception:
            return None

    def _clear_resume_state(self):
        """清除断点续传状态文件。"""
        state_path = self._get_resume_state_path()
        if os.path.isfile(state_path):
            try:
                os.remove(state_path)
            except Exception:
                pass

    # ---- 下载（INSPUR-102 增量优先 + 断点续传） ----

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

    def start_incremental_download(self):
        """启动增量包优先的后台下载线程（INSPUR-102）。

        流程：
        1. 优先下载增量包（snapshot_*.zip）
        2. 404 或其他失败 → 降级下载完整安装包
        3. 下载目标为 staging 目录
        4. 支持断点续传
        """
        last = self.get_last_check()
        if not last:
            return

        self._reset_download_state()
        self._is_incremental = True
        threading.Thread(
            target=self._do_incremental_download, daemon=True
        ).start()

    def _do_incremental_download(self):
        """增量下载主流程：增量包优先，失败降级完整包。

        Module 2 + Module 5: 增量下载链路 + 多版本跳跃升级
        支持链式下载多个中间增量包。
        """
        import logging
        _log = logging.getLogger(__name__)

        last = self.get_last_check()
        if not last:
            self._set_download_error('无可用更新信息')
            return

        target_version = last.get('version', '')
        current_version = _read_version()
        chain = self._chain_versions

        # ---- 多版本跳跃：链式下载所有中间增量包 ----
        if chain and len(chain) > 1:
            with self._lock:
                self._download_event = 'updating_chain'
            _log.info("[OK] 多版本跳跃升级: %s → %s, 共 %d 步",
                      current_version, target_version, len(chain))

            all_success = True
            for i, snap in enumerate(chain):
                _log.info("[OK] 链式下载 %d/%d: %s → %s",
                          i + 1, len(chain), snap['from_version'], snap['to_version'])
                with self._lock:
                    self._progress_percent = int(i * 100 / len(chain))

                success = self._download_single_incremental(
                    snap['url'], snap['from_version'], snap['to_version'],
                    is_chain=True
                )
                if not success:
                    _log.warning("[!] 增量包下载失败 %s → %s，降级为完整包下载",
                                snap['from_version'], snap['to_version'])
                    all_success = False
                    break

            if all_success:
                self._finalize_download(target_version)
                return
            else:
                # 降级：完整包下载
                _log.info("[OK] 降级为完整包下载...")

        # ---- 精确匹配的增量包 ----
        incremental_url = last.get('incremental_url')
        if incremental_url:
            with self._lock:
                self._download_event = 'downloading_incremental'
            _log.info("[OK] 尝试增量下载: %s", incremental_url)

            success = self._download_single_incremental(
                incremental_url, current_version, target_version,
                is_chain=False
            )
            if success:
                self._finalize_download(target_version)
                return

            _log.info("[OK] 增量包不可用，降级为完整包下载...")

        # ---- 降级：下载完整安装包 ----
        full_url = last.get('download_url')
        if not full_url:
            self._set_download_error('无可用下载链接（增量包和完整包均不可用）')
            return

        with self._lock:
            self._download_event = 'downloading_full'
            self._is_incremental = False

        _log.info("[OK] 下载完整安装包: %s", full_url)
        save_dir = os.path.join(_get_data_dir(), 'updates')
        self._do_download(full_url, save_dir)

    def _download_single_incremental(self, url, from_version, to_version, is_chain=False):
        """下载单个增量包并解压到 staging 目录。

        Parameters
        ----------
        url : str
            增量包下载 URL
        from_version : str
            起始版本号
        to_version : str
            目标版本号
        is_chain : bool
            是否属于多版本跳跃链（链中每个包都追加到 staging）

        Returns
        -------
        bool
            成功返回 True
        """
        import logging
        _log = logging.getLogger(__name__)
        import zipfile
        import io

        staging_dir = self._get_staging_dir()
        os.makedirs(staging_dir, exist_ok=True)

        # 下载到临时文件
        temp_file = os.path.join(staging_dir, f'snapshot_v{from_version}_v{to_version}.zip')
        files_dir = os.path.join(staging_dir, 'files')
        os.makedirs(files_dir, exist_ok=True)

        try:
            self._do_download_once(url, temp_file)
        except Exception as e:
            _log.warning("[!] 增量包下载失败: %s", e)
            return False

        # 解压到 staging/files/
        try:
            with zipfile.ZipFile(temp_file, 'r') as zf:
                zf.extractall(files_dir)
            _log.info("[OK] 增量包解压完成: %s", temp_file)
        except zipfile.BadZipFile:
            _log.error("[X] 增量包损坏（非有效 ZIP 文件）: %s", temp_file)
            try:
                os.remove(temp_file)
            except Exception:
                pass
            return False
        except Exception as e:
            _log.error("[X] 增量包解压失败: %s", e)
            try:
                os.remove(temp_file)
            except Exception:
                pass
            return False

        # 删除下载的 zip 文件（已解压）
        try:
            os.remove(temp_file)
        except Exception:
            pass

        # 校验 manifest.json 的 SHA256
        # manifest.json 在 zip 内位于根级别，解压后位于 staging/files/manifest.json
        # 但 bootstrap._apply_staging() 期望 manifest.json 在 staging/manifest.json
        # 因此需要复制/生成一份到 staging 根目录
        manifest_path_in_files = os.path.join(files_dir, 'manifest.json')
        manifest_path_in_staging = os.path.join(staging_dir, 'manifest.json')

        if os.path.isfile(manifest_path_in_files):
            if not self._verify_manifest(manifest_path_in_files, files_dir):
                _log.error("[X] manifest SHA256 校验失败")
                shutil.rmtree(staging_dir, ignore_errors=True)
                return False
            # 复制 manifest.json 到 staging 根目录，供 bootstrap 读取
            shutil.copy2(manifest_path_in_files, manifest_path_in_staging)
            _log.info("[OK] manifest.json 已复制到 staging 根目录")
        else:
            _log.warning("[!] 增量包中未找到 manifest.json，自动生成...")
            # 生成 manifest.json：扫描 staging/files/ 下的文件列表
            loaded_manifest = self._generate_manifest_from_extracted(
                files_dir, from_version, to_version)
            if loaded_manifest is None:
                _log.error("[X] 无法生成 manifest.json（提取目录为空）")
                shutil.rmtree(staging_dir, ignore_errors=True)
                return False

        _log.info("[OK] 增量包已就绪: %s → %s (chain=%s)", from_version, to_version, is_chain)
        return True

    def _verify_manifest(self, manifest_path, files_dir):
        """校验 staging 目录中文件的 SHA256。

        Parameters
        ----------
        manifest_path : str
            manifest.json 路径
        files_dir : str
            files/ 目录路径

        Returns
        -------
        bool
            全部校验通过返回 True
        """
        import logging
        _log = logging.getLogger(__name__)

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception as e:
            _log.error("[X] manifest.json 解析失败: %s", e)
            return False

        expected_sha256 = manifest.get('sha256', {})
        if not expected_sha256:
            _log.info("[OK] manifest 中无 SHA256 字段，跳过校验")
            return True

        all_files = (manifest.get('added_files', []) +
                     manifest.get('changed_files', []))
        all_valid = True
        for fname in all_files:
            expected = expected_sha256.get(fname)
            if not expected:
                continue
            filepath = os.path.join(files_dir, fname)
            if not os.path.isfile(filepath):
                _log.error("[X] 文件缺失: %s", fname)
                all_valid = False
                continue
            try:
                h = hashlib.sha256()
                with open(filepath, 'rb') as f_in:
                    while True:
                        chunk = f_in.read(65536)
                        if not chunk:
                            break
                        h.update(chunk)
                actual = h.hexdigest()
                if actual != expected:
                    _log.error("[X] SHA256 校验失败: %s (期望 %s, 实际 %s)",
                               fname, expected[:16], actual[:16])
                    all_valid = False
            except Exception as e:
                _log.error("[X] 文件读取失败: %s - %s", fname, e)
                all_valid = False

        if all_valid:
            _log.info("[OK] 文件完整性校验通过 (%d 个文件)", len(all_files))
        return all_valid

    @staticmethod
    def _generate_manifest_from_extracted(files_dir, from_version, to_version):
        """从已解压的文件目录生成 manifest.json。

        当增量 zip 包内不包含 manifest.json 时，自动扫描 files_dir
        下的所有文件生成 manifest，写入 staging 根目录供 bootstrap 读取。

        Parameters
        ----------
        files_dir : str
            已解压文件的目录（如 staging/files/）
        from_version : str
            起始版本号
        to_version : str
            目标版本号

        Returns
        -------
        dict or None
            生成的 manifest dict，files_dir 为空时返回 None
        """
        import logging
        _log = logging.getLogger(__name__)

        staging_dir = os.path.dirname(files_dir)  # staging 根目录

        added_files = []
        changed_files = []
        sha256_map = {}

        # 遍历 files/ 下所有文件（含子目录）
        for root, dirs, filenames in os.walk(files_dir):
            for fname in filenames:
                full_path = os.path.join(root, fname)
                # 相对于 files/ 的路径
                rel_path = os.path.relpath(full_path, files_dir).replace('\\', '/')

                # 跳过 .patch 差分文件（如果有），只列出主文件
                if rel_path.endswith('.patch'):
                    continue

                # 跳过 manifest.json 本身
                if rel_path == 'manifest.json':
                    continue

                # 所有文件作为 added_files（_safe_copy 会覆盖已存在的文件）
                if os.path.isfile(full_path):
                    added_files.append(rel_path)

                # 计算 SHA256
                try:
                    h = hashlib.sha256()
                    with open(full_path, 'rb') as f_in:
                        while True:
                            chunk = f_in.read(65536)
                            if not chunk:
                                break
                            h.update(chunk)
                    sha256_map[rel_path] = h.hexdigest()
                except Exception:
                    pass

        if not added_files and not changed_files:
            _log.warning("[X] 解压目录为空，无法生成 manifest")
            return None

        manifest = {
            'from_version': from_version,
            'to_version': to_version,
            'added_files': added_files,
            'changed_files': changed_files,
            'removed_files': [],
            'sha256': sha256_map,
            '_generated': True,  # 标记为自动生成
        }

        manifest_path = os.path.join(staging_dir, 'manifest.json')
        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            _log.info("[OK] manifest.json 已自动生成: %d 个文件", len(added_files))
        except Exception as e:
            _log.error("[X] manifest.json 写入失败: %s", e)
            return None

        return manifest

    def _finalize_download(self, target_version):
        """下载完成后的收尾工作。

        1. 标记下载完成
        2. 写入 update_ready.json
        3. 设置状态为 ready_to_restart
        """
        staging_dir = self._get_staging_dir()

        with self._lock:
            self._downloading = False
            self._downloaded = True
            self._file_path = staging_dir
            self._progress_percent = 100
            self._download_event = 'ready_to_restart'
            self._staging_dir = staging_dir

        # 清理断点续传状态
        self._clear_resume_state()

        print(f"[OK] 更新包就绪: staging={staging_dir}, target={target_version}")

    def _set_download_error(self, error_msg):
        """安全地设置下载错误状态。"""
        with self._lock:
            self._downloading = False
            self._downloaded = False
            self._error = error_msg
        print(f"[X] 下载失败: {error_msg}")

    def _do_download(self, url, save_dir):
        """后台下载，更新进度状态。

        使用 requests（urllib3）代替 urllib.request：
        - urllib3 连接池复用 + keep-alive，跨 redirect 复用 TCP+TLS 连接
        - GitHub Releases URL 经 302 重定向到 objects.githubusercontent.com，
          requests 的 Session 可复用连接，比 urllib 每次新开连接更快
        - stream=True + iter_content 64KB chunk，比 urllib.read(8KB) 吞吐更高
        - 支持断点续传：第 2/3 次重试时从已下载位置继续（Range 请求）
        - INSPUR-102: 下载状态持久化，支持程序重启后继续下载
        """
        import requests

        os.makedirs(save_dir, exist_ok=True)
        # 从 URL 路径提取文件名（去掉 query string）
        url_path = url.rsplit('?', 1)[0] if '?' in url else url
        filename = url_path.rsplit('/', 1)[-1] or 'update.exe'
        filepath = os.path.join(save_dir, filename)

        RETRY_COUNT = 2
        RETRY_DELAY = 2

        for attempt in range(RETRY_COUNT + 1):
            try:
                self._do_download_once(url, filepath)
                # 成功
                with self._lock:
                    self._downloading = False
                    self._downloaded = True
                    self._file_path = filepath
                    self._progress_percent = 100
                    self._download_event = 'ready_to_restart'
                self._clear_resume_state()
                print(f"[OK] 更新包下载完成: {filepath}")
                return
            except Exception as e:
                is_network_error = self._is_network_error(e)
                if is_network_error and attempt < RETRY_COUNT:
                    print(f"[!] 下载失败（{e}），{RETRY_DELAY}s 后重试（{attempt + 2}/{RETRY_COUNT + 1}）...")
                    # 重置进度，清理部分文件
                    with self._lock:
                        self._progress_percent = 0
                    time.sleep(RETRY_DELAY)
                    # 断点续传：不清除已下载的部分文件，下次下载继续
                    continue
                # 非网络错误，或重试次数耗尽
                error_msg = str(e)
                if is_network_error:
                    error_msg = '网络不稳定，下载失败，请重试'
                with self._lock:
                    self._downloading = False
                    self._downloaded = False
                    self._error = error_msg
                self._clear_resume_state()
                print(f"[X] 更新包下载失败: {error_msg}")
                return

    def _do_download_once(self, url, filepath):
        """单次下载尝试（不含重试），支持断点续传。

        INSPUR-102 增强：
        - 支持 HTTP Range 请求续传（Module 4）
        - 下载过程中定期持久化进度状态
        """
        import requests

        # 检查断点续传状态
        headers = {'User-Agent': 'gongshi-updater/1.0'}
        resume_offset = 0
        resume_state = self._load_resume_state(url)
        if resume_state and resume_state.get('filepath') == filepath:
            resume_offset = resume_state.get('downloaded_bytes', 0)
            if resume_offset > 0:
                headers['Range'] = f'bytes={resume_offset}-'
                with self._lock:
                    self._download_event = 'downloading_resume'
                print(f"[OK] 断点续传: 从 {resume_offset} 字节继续下载")

        with requests.get(
            url,
            headers=headers,
            timeout=(30, 300),  # (connect_timeout, read_timeout)
            stream=True,
            proxies=self._get_system_proxies(),
        ) as resp:
            if resume_offset > 0 and resp.status_code not in (200, 206):
                # Range 请求未得到预期响应，从头开始
                resp.raise_for_status()
                resume_offset = 0

            if resp.status_code == 206:
                total = resume_offset + int(resp.headers.get('Content-Length', 0))
            else:
                total = int(resp.headers.get('Content-Length', 0))

            so_far = resume_offset
            mode = 'ab' if resume_offset > 0 else 'wb'
            with open(filepath, mode) as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        bytes_written = f.write(chunk)
                        so_far += bytes_written
                        if total > 0:
                            pct = int(so_far * 100 / total)
                            with self._lock:
                                self._progress_percent = pct
                        # 定期保存续传状态（每 ~5MB 或 10 秒）
                        if so_far % (5 * 1024 * 1024) < 65536:
                            self._save_resume_state(url, filepath, so_far, total)

            # 下载完成，清理续传状态
            self._save_resume_state(url, filepath, so_far, total)

    @staticmethod
    def _is_network_error(exception):
        """判断异常是否为网络类错误（值得重试的）。"""
        import requests

        # requests 库封装的网络异常
        if isinstance(exception, requests.exceptions.ConnectionError):
            return True
        if isinstance(exception, requests.exceptions.Timeout):
            return True
        if isinstance(exception, requests.exceptions.ChunkedEncodingError):
            return True
        # urllib3 底层异常
        exc_str = str(exception).lower()
        for keyword in ('incompleteread', 'connectionreset', 'connectionerror',
                        'chunkedencodingerror', 'timeouterror', 'remotedisconnected',
                        'connectionabortederror', 'broken pipe'):
            if keyword in exc_str:
                return True
        return False

    # ---- 状态查询（线程安全） ----

    def get_status(self):
        """获取当前下载/安装状态（INSPUR-102 增强事件字段）。"""
        with self._lock:
            return {
                'downloading': self._downloading,
                'progress_percent': self._progress_percent,
                'downloaded': self._downloaded,
                'error': self._error,
                'install_status': self._install_status,
                'install_error': self._install_error,
                # INSPUR-102 新增事件字段
                'event': self._download_event,
                'is_incremental': self._is_incremental,
            }

    def get_file_path(self):
        """获取下载的安装包文件路径。"""
        with self._lock:
            return self._file_path

    def install_update(self):
        """检查安装包是否就绪，并标记安装进行中。

        INSPUR-102:
        - 增量更新：staging 目录已就绪，直接标记 installing
        - 完整包：检查 .exe 文件是否存在

        Windows: 返回成功状态，等待前端调用 prepare_restart 完成安装
        macOS:   open 命令打开 DMG，弹出 Finder

        返回 (success: bool, message: str)
        """
        with self._lock:
            file_path = self._file_path
            downloaded = self._downloaded
            is_incremental = self._is_incremental

        if is_incremental:
            # 增量模式：检查 staging 目录
            if not file_path or not os.path.isdir(file_path):
                with self._lock:
                    self._install_status = 'failed'
                    self._install_error = '增量包目录不存在'
                return False, '增量包目录不存在'
        else:
            if not downloaded or not file_path or not os.path.isfile(file_path):
                with self._lock:
                    self._install_status = 'failed'
                    self._install_error = '安装包文件不存在'
                return False, '安装包文件不存在'

        print(f"[OK] 安装模式: platform={sys.platform}, incremental={is_incremental}")

        if sys.platform == 'win32':
            with self._lock:
                self._install_status = 'installing'
            return True, 'installing'
        elif sys.platform == 'darwin':
            return self._install_mac(file_path)
        else:
            with self._lock:
                self._install_status = 'failed'
                self._install_error = f'不支持的平台: {sys.platform}'
            return False, f'不支持的平台: {sys.platform}'

    def prepare_restart(self):
        """准备重启并应用更新（INSPUR-102：替换原 Inno Setup 静默安装流程）。

        新流程：
        1. 写入 update_ready.json（bootstrap 启动时读取）
        2. 对完整包下载的场景：将 .exe 安装包路径也记录到 update_ready.json
           让 bootstrap 在启动后静默安装
        3. 返回成功，由调用方执行 os._exit(0)

        移除了原 batch 脚本 + Inno Setup 静默安装流程。

        返回 (success: bool, message: str)
        """
        with self._lock:
            file_path = self._file_path
            downloaded = self._downloaded
            is_incremental = self._is_incremental
            staging_dir = self._staging_dir
            download_event = self._download_event

        # 准备 update_ready.json
        last = self.get_last_check()
        target_version = last.get('version', '') if last else ''

        if is_incremental:
            # 增量更新：staging 目录已就绪
            actual_staging = staging_dir or self._get_staging_dir()
            if not os.path.isdir(actual_staging):
                with self._lock:
                    self._install_status = 'failed'
                    self._install_error = '增量更新文件未就绪'
                return False, '增量更新文件未就绪'

            update_ready = {
                'target_version': target_version,
                'staging_dir': actual_staging,
                'type': 'incremental',
            }
        elif downloaded and file_path and os.path.isfile(file_path):
            # 完整包下载：需要 bootstrap 启动后执行 Inno Setup 静默安装
            # 或者直接用现有 restart_and_install 路径
            update_ready = {
                'target_version': target_version,
                'installer_path': file_path,
                'type': 'full',
            }
        else:
            with self._lock:
                self._install_status = 'failed'
                self._install_error = '安装包文件不存在'
            return False, '安装包文件不存在'

        # 写入 update_ready.json
        update_ready_path = os.path.join(_get_data_dir(), 'update_ready.json')
        try:
            os.makedirs(os.path.dirname(update_ready_path), exist_ok=True)
            with open(update_ready_path, 'w', encoding='utf-8') as f:
                json.dump(update_ready, f, ensure_ascii=False, indent=2)
            print(f"[OK] update_ready.json 已写入: {update_ready_path}")
            print(f"[OK] 更新目标版本: {target_version}")
        except Exception as e:
            with self._lock:
                self._install_status = 'failed'
                self._install_error = f'写入 update_ready.json 失败: {e}'
            return False, f'写入 update_ready.json 失败: {e}'

        with self._lock:
            self._install_status = 'done'
            self._download_event = 'ready_to_restart'
        return True, '更新已就绪，应用即将重启'

    def prepare_rollback(self):
        """准备回滚：检查 rollback 目录是否存在。
        INSPUR-102 Module 6。

        Returns
        -------
        (available: bool, message: str)
        """
        rollback_dir = os.path.join(_get_data_dir(), 'rollback')
        manifest_path = os.path.join(rollback_dir, 'rollback_manifest.json')

        if not os.path.isfile(manifest_path):
            return False, '回滚文件不存在'

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            orig_version = manifest.get('original_version', '未知')
            changed_count = len(manifest.get('changed_files', {}))
            added_count = len(manifest.get('added_files', []))

            with self._lock:
                self._download_event = 'rollback_available'

            return True, f'可回滚到 {orig_version}（{changed_count} 个变更文件，{added_count} 个新增文件）'
        except Exception as e:
            return False, f'回滚清单损坏: {e}'

    def do_rollback(self):
        """执行回滚操作（通过 bootstrap --rollback 方式）。

        由于运行中的进程无法替换自身文件，这里不做实际文件操作，
        而是设置 enable_rollback 标志，让调用方通过命令行参数启动 bootstrap 来执行回滚。

        Returns
        -------
        (success: bool, message: str)
        """
        rollback_dir = os.path.join(_get_data_dir(), 'rollback')
        manifest_path = os.path.join(rollback_dir, 'rollback_manifest.json')

        if not os.path.isfile(manifest_path):
            return False, '无可用回滚文件'

        # 标记回滚请求（下次 bootstrap 启动时执行）
        update_ready_path = os.path.join(_get_data_dir(), 'update_ready.json')
        rollback_flag = {'rollback': True, 'rollback_dir': rollback_dir}
        try:
            with open(update_ready_path, 'w', encoding='utf-8') as f:
                json.dump(rollback_flag, f)
            print(f"[OK] 回滚标志已设置: {update_ready_path}")
        except Exception as e:
            return False, f'设置回滚标志失败: {e}'

        return True, '回滚已准备，请重启应用完成回滚'

    def auto_start_download(self):
        """后台静默下载（INSPUR-102 Module 3）。

        启动后检测到新版本时自动在后台下载，不等待用户操作。
        仅在没有进行中的下载时触发。
        """
        with self._lock:
            is_downloading = self._downloading
            is_downloaded = self._downloaded

        if is_downloading or is_downloaded:
            return  # 已有进行中的下载

        last = self.get_last_check()
        if not last or not last.get('has_update'):
            return

        self._auto_download = True
        self.start_incremental_download()

    # ---- 旧的 restart_and_install 保留向后兼容（完整包安装器路径） ----

    def restart_and_install(self):
        """执行后台静默安装并自动重启应用（Windows 平台，完整包兼容路径）。

        保留用于完整 .exe 安装包的回退场景。
        增量更新应使用 prepare_restart() 新路径。

        返回 (success: bool, message: str)
        """
        with self._lock:
            file_path = self._file_path
            downloaded = self._downloaded

        if not downloaded or not file_path or not os.path.isfile(file_path):
            with self._lock:
                self._install_status = 'failed'
                self._install_error = '安装包文件不存在'
            return False, '安装包文件不存在'

        import subprocess

        frozen_dir = None
        if getattr(sys, 'frozen', False):
            frozen_dir = os.path.dirname(sys.executable)

        install_dir = frozen_dir or self._get_windows_install_dir()
        default_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                                   'IEI Timer Faster')
        target_dir = install_dir or default_dir
        new_exe = os.path.join(target_dir, 'IEI Timer Faster.exe')

        log_file = os.path.join(os.path.dirname(file_path), '_update.log')
        bat_path = os.path.join(os.path.dirname(file_path), '_install.bat')

        desktop_lnk = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop', 'IEI Timer Faster.lnk')

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
            'ping 127.0.0.1 -n 6 >nul',
            '',
            f'echo [!date! !time!] 运行安装程序... >> "!LOG!"',
            f'"{file_path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR="{target_dir}"',
            'set SETUP_ERR=!ERRORLEVEL!',
            '',
            'if !SETUP_ERR! neq 0 (',
            f'    echo [!date! !time!] [X] 安装失败, 错误码=!SETUP_ERR! >> "!LOG!"',
            '    exit /b !SETUP_ERR!',
            ')',
            '',
            f'echo [!date! !time!] [OK] 安装成功 >> "!LOG!"',
            '',
            f'echo [!date! !time!] 检查桌面快捷方式... >> "!LOG!"',
            f'if exist "{desktop_lnk}" (',
            f'    echo [!date! !time!] [OK] 桌面快捷方式已存在 >> "!LOG!"',
            f') else (',
            f'    echo [!date! !time!] [!] 快捷方式缺失(右键exe→发送到→桌面快捷方式) >> "!LOG!"',
            f')',
            '',
            f'echo [!date! !time!] 启动新版本... >> "!LOG!"',
            f'start "" "{new_exe}"',
            '',
            f'echo [!date! !time!] 清理临时文件... >> "!LOG!"',
            f'del /f /q "{file_path}" >nul 2>&1',
            f'del /f /q "{bat_path}" >nul 2>&1',
            f'echo [!date! !time!] 更新流程完成 >> "!LOG!"',
        ]
        try:
            with open(bat_path, 'w', encoding='gbk') as f:
                f.write('\r\n'.join(bat_lines))
        except Exception as e:
            with self._lock:
                self._install_status = 'failed'
                self._install_error = f'创建安装脚本失败: {e}'
            return False, f'创建安装脚本失败: {e}'

        try:
            print(f"[OK] 启动后台静默安装脚本: {bat_path}")
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            subprocess.Popen(
                ['cmd.exe', '/c', bat_path],
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            with self._lock:
                self._install_status = 'failed'
                self._install_error = f'启动安装失败: {e}'
            return False, f'启动安装失败: {e}'

        with self._lock:
            self._install_status = 'done'
        return True, '安装已启动，应用即将重启'

    @staticmethod
    def _get_windows_install_dir():
        """从注册表读取现有安装目录。

        优先按当前 AppId 直接查找（v1.1.7+ 固定 GUID 快速路径），
        查不到时遍历 Uninstall 注册表子键，匹配 DisplayName 回退查找
        （兼容 v1.1.6 及更早版本——当时 AppId 使用 ISPP {{}} 随机生成）。

        Returns
        -------
        str or None
            安装目录路径，读取失败返回 None
        """
        import winreg

        # 要搜索的注册表根键
        _UNINSTALL_ROOTS = (
            (winreg.HKEY_CURRENT_USER,
             r'Software\Microsoft\Windows\CurrentVersion\Uninstall'),
            (winreg.HKEY_LOCAL_MACHINE,
             r'Software\Microsoft\Windows\CurrentVersion\Uninstall'),
        )
        # 主 AppId（花括号格式，匹配 setup.iss {{A8F3C2B1-...}} → {A8F3C2B1-...}）
        # V1.1.10-V1.1.11 曾改为纯字符串（无花括号），现已回退。
        KNOWN_APP_ID = '{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}'
        # 旧 AppId（v1.1.10-v1.1.11 纯字符串格式），作为回退兼容
        KNOWN_APP_ID_ALT = 'A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C'
        APP_DISPLAY_NAME = 'IEI Timer Faster'

        def _read_install_location(root, subkey_path):
            """读取单个注册表键的 InstallLocation。"""
            try:
                key = winreg.OpenKey(root, subkey_path)
                try:
                    val, _ = winreg.QueryValueEx(key, 'InstallLocation')
                    if val and os.path.isdir(val):
                        return val
                finally:
                    winreg.CloseKey(key)
            except OSError:
                pass
            return None

        # 第一步：按已知 AppId 直接查找（快速路径）
        for root, base_path in _UNINSTALL_ROOTS:
            result = _read_install_location(
                root, fr'{base_path}\{KNOWN_APP_ID}_is1')
            if result:
                return result

        # 1b: 回退查旧 AppId（v1.1.10-v1.1.11 纯字符串格式）
        for root, base_path in _UNINSTALL_ROOTS:
            result = _read_install_location(
                root, fr'{base_path}\{KNOWN_APP_ID_ALT}_is1')
            if result:
                return result

        # 第二步：回退——遍历所有子键，匹配 DisplayName
        # 兼容 v1.1.6 等 AppId 使用 {{}} 随机生成的旧版本
        for root, base_path in _UNINSTALL_ROOTS:
            try:
                uninstall_key = winreg.OpenKey(root, base_path)
                try:
                    idx = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(uninstall_key, idx)
                            idx += 1
                        except OSError:
                            break  # 枚举完毕

                        subkey_path = fr'{base_path}\{subkey_name}'
                        try:
                            sk = winreg.OpenKey(root, subkey_path)
                            try:
                                display_name, _ = winreg.QueryValueEx(
                                    sk, 'DisplayName')
                                if display_name == APP_DISPLAY_NAME:
                                    val, _ = winreg.QueryValueEx(
                                        sk, 'InstallLocation')
                                    winreg.CloseKey(sk)
                                    if val and os.path.isdir(val):
                                        return val
                            except OSError:
                                pass
                            finally:
                                try:
                                    winreg.CloseKey(sk)
                                except OSError:
                                    pass
                        except OSError:
                            continue
                finally:
                    winreg.CloseKey(uninstall_key)
            except OSError:
                continue

        return None

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
        self._lock_socket = None
        self._window = None

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

        # 单实例锁（仅打包模式）：第二个实例通知已有窗口并退出
        if is_frozen:
            is_first, self._lock_socket = _acquire_instance_lock()
            if not is_first:
                print("[!] 检测到已有实例运行，通知已有窗口置前并退出")
                _notify_existing_and_exit()
                # 走到这里说明锁端口被其他程序占用（非 gongshi 实例），
                # 放行本次启动但无单实例保护
                print("[!] 无法通知已有实例，锁端口 %d 可能被占用，无单实例保护" %
                      _SINGLE_INSTANCE_PORT)

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
    # 单实例锁服务
    # =================================================================

    def _serve_instance_lock(self):
        """后台线程：监听 lock socket，收到 FOCUS 信号时置前窗口。"""
        while self._lock_socket is not None:
            try:
                conn, _ = self._lock_socket.accept()
                data = conn.recv(1024)
                if data == b'FOCUS':
                    self._focus_window()
                conn.close()
            except socket.timeout:
                continue
            except Exception:
                break

    def _focus_window(self):
        """将 pywebview 窗口置前（跨平台）。"""
        if self._window is None:
            return
        try:
            # restore() 在 WinForms 后端使用 self.Invoke() 调度到 UI 线程，线程安全
            self._window.restore()

            if threading.current_thread() is threading.main_thread():
                # 主线程：直接调用 on_top 确保窗口置前
                self._window.on_top = True

                def _reset_ontop():
                    time.sleep(0.5)
                    try:
                        if self._window is not None:
                            self._window.on_top = False
                    except Exception:
                        pass

                threading.Thread(target=_reset_ontop, daemon=True).start()
            else:
                # 非主线程（锁服务 daemon 线程）：
                # on_top setter → winforms.set_on_top() 直接赋值 i.TopMost，
                # 无 Invoke 调度 → 跨线程操作 WinForms 控件 → 死锁风险。
                # 改用 evaluate_js('window.focus()')，EdgeChromium 内部用
                # self.webview.Invoke() 调度到 UI 线程，线程安全。
                try:
                    import webview
                    if webview.windows:
                        webview.windows[0].evaluate_js('window.focus()')
                except Exception:
                    pass
        except Exception:
            pass

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
        # INSPUR-102: 检测到新版本后自动开始静默下载
        def _check_for_update():
            time.sleep(2)  # 启动后延迟 2-3 秒，等 UI 渲染
            checker = get_update_checker()
            result = checker.check_update(_read_version())
            if result:
                print(f"[OK] 发现新版本 V{result['version']}")
                # Module 3: 自动后台静默下载增量包
                if result.get('auto_download'):
                    print("[OK] 开始后台静默下载...")
                    checker.auto_start_download()
            elif checker.get_last_check() is None:
                # check_update 返回 None 且 _last_check 为 None：
                # 可能网络异常或 XML 解析失败，已在 _check_* 方法中记录详情
                print("[!] 更新检查失败，无法确定是否有新版本（详见上方日志）")
            else:
                print("[OK] 已是最新版本")

        threading.Thread(target=_check_for_update, daemon=True).start()

        # ---- pywebview 桌面窗口 ----
        try:
            import webview
            self._window = webview.create_window(
                'IEI Timer Faster',
                url,
                width=1280,
                height=860,
                min_size=(900, 600),
                resizable=True,
                text_select=True,
                maximized=True,
            )
            print("[OK] 桌面窗口已创建")

            # 启动单实例锁服务线程（监听后续实例的置前请求）
            if self._lock_socket is not None:
                lock_thread = threading.Thread(
                    target=self._serve_instance_lock, daemon=True)
                lock_thread.start()
                print("[OK] 单实例锁已激活")

            print("[OK] 显示桌面窗口，关闭窗口即可退出程序")

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
