# -*- coding: utf-8 -*-
"""
License 激活模块 — 共享工具函数

供 app.py（Web 端验证）和 tools/license_generator.py（管理端生成）共用。

算法方案（老王确认，2026-06-25）：
  - SN：base64(username)，不做设备绑定
  - License 格式：Base64(JSON).HMAC-SHA256签名前16位hex
  - License 内容：JSON payload {sn, exp, type}
  - 状态存储：本地 license_status.json（Flask debug 重启不丢失）
  - 密钥管理：复用 RDM_SECRET_KEY 环境变量
"""

import os
import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta


# ===========================================================================
# 密钥管理
# ===========================================================================

def _get_secret_key() -> bytes:
    """
    获取 License 签名密钥。

    优先级：
      1. 环境变量 RDM_SECRET_KEY（生产环境应配置）
      2. 内置默认密钥（仅开发环境使用）

    注意：更换密钥会导致所有已签发 License 失效。
    """
    key = os.environ.get('RDM_SECRET_KEY', '')
    if key:
        return key.encode('utf-8')
    # 开发环境默认密钥
    return b'gongshi_license_default_key_2026'


# ===========================================================================
# SN 生成
# ===========================================================================

def generate_sn(username: str) -> str:
    """
    基于用户名生成 SN 码。

    算法：base64(username)，不做硬件绑定（Web 端无法可靠获取硬件序列号）。
    用户将 SN 码发给管理员以获取 License。
    """
    if not username:
        return ''
    return base64.b64encode(username.encode('utf-8')).decode('utf-8')


# ===========================================================================
# License 生成
# ===========================================================================

def generate_license(sn: str, duration_type: str) -> str:
    """
    生成 License 字符串。

    参数：
        sn            — SN 码（由 generate_sn() 生成）
        duration_type — '1年' 或 '永久'

    返回 License 字符串，格式：Base64(JSON).签名hex前16位

    JSON payload 结构：
        {"sn": "<sn>", "type": "<1年|永久>", "exp": "<ISO日期>"|null}
    """
    if not sn:
        raise ValueError("SN 码不能为空")
    if duration_type not in ('1年', '永久'):
        raise ValueError("时长类型必须为 '1年' 或 '永久'")

    # 构造 payload
    payload = {
        'sn': sn,
        'type': duration_type,
    }

    if duration_type == '1年':
        exp_date = datetime.now() + timedelta(days=365)
        payload['exp'] = exp_date.strftime('%Y-%m-%dT00:00:00')
    else:
        payload['exp'] = None

    # JSON → Base64（紧凑格式，无空格）
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    payload_b64 = base64.b64encode(payload_json.encode('utf-8')).decode('utf-8')

    # HMAC-SHA256 签名
    key = _get_secret_key()
    sig_full = hmac.new(key, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    sig_short = sig_full[:16]  # 取前 16 位 hex

    return f"{payload_b64}.{sig_short}"


# ===========================================================================
# License 验证
# ===========================================================================

def verify_license(license_str: str):
    """
    验证 License 字符串。

    参数：
        license_str — License 字符串（格式：Base64(JSON).签名hex前16位）

    返回：
        (valid: bool, payload: dict|None, error: str|None)

        valid=True   → payload 为解析后的 JSON dict
        valid=False  → error 为失败原因（中文）
    """
    if not license_str or '.' not in license_str:
        return False, None, 'License 格式无效'

    # 从右侧分割（payload 本身不包含 '.'，签名部分不含 '.'）
    parts = license_str.rsplit('.', 1)
    if len(parts) != 2:
        return False, None, 'License 格式无效'
    payload_b64, sig_provided = parts

    # 1. 验证签名
    key = _get_secret_key()
    sig_expected = hmac.new(
        key, payload_b64.encode('utf-8'), hashlib.sha256
    ).hexdigest()[:16]

    if not hmac.compare_digest(sig_provided, sig_expected):
        return False, None, 'License 签名验证失败，可能被篡改'

    # 2. 解析 payload
    try:
        payload_json = base64.b64decode(payload_b64).decode('utf-8')
        payload = json.loads(payload_json)
    except Exception:
        return False, None, 'License 内容解析失败'

    # 3. 校验必填字段
    if 'sn' not in payload:
        return False, None, 'License 缺少 SN 字段'
    if 'type' not in payload:
        return False, None, 'License 缺少类型字段'

    # 4. 校验过期时间
    exp = payload.get('exp')
    if exp is not None:
        try:
            exp_date = datetime.strptime(exp[:10], '%Y-%m-%d')
            if datetime.now() > exp_date:
                return False, payload, 'License 已过期（%s）' % exp[:10]
        except ValueError:
            return False, payload, 'License 过期时间格式错误'

    return True, payload, None


# ===========================================================================
# 激活状态存储（license_status.json）
#
# 存储格式（INSPUR-57 升级后）：
#   {
#     "<sn>": {"activated": true, "sn": "<sn>", "type": "1年", ...},
#     "<sn2>": {"activated": true, "sn": "<sn2>", "type": "永久", ...}
#   }
#
# 旧格式（INSPUR-57 之前）：
#   {"activated": true, "sn": "<sn>", "type": "1年", ...}
#
# _read_all_status() 自动检测旧格式并迁移为新格式。
# ===========================================================================


def _get_status_file_path() -> str:
    """
    获取 license_status.json 的完整路径。

    - PyInstaller 打包模式（sys.frozen）：
        Windows: %APPDATA%/gongshi/license_status.json
        macOS:   ~/Library/Application Support/gongshi/license_status.json
        其他:    ~/gongshi/license_status.json
    - 开发模式：与 license_utils.py 同目录，跟历史行为兼容。
    """
    import sys
    if getattr(sys, 'frozen', False):
        # 桌面打包模式 → 用户数据目录
        if sys.platform == 'darwin':
            data_dir = os.path.join(
                os.path.expanduser('~'), 'Library', 'Application Support', 'gongshi')
        elif sys.platform == 'win32':
            appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
            data_dir = os.path.join(appdata, 'gongshi')
        else:
            data_dir = os.path.join(os.path.expanduser('~'), 'gongshi')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'license_status.json')
    # 开发模式 → 与 license_utils.py 同目录
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'license_status.json'
    )


def _read_all_status() -> dict:
    """
    读取全量激活状态字典（{sn: status, ...}）。

    自动迁移逻辑：
      如果文件顶层含有 'activated' 键（旧单记录格式），
      自动包装为 {old_sn: old_data} 并写回文件。

    文件不存在或损坏时返回空字典 {}。
    """
    path = _get_status_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, Exception):
        return {}

    if not isinstance(data, dict):
        return {}

    # 自动迁移：检测旧格式（顶层有 'activated' 键）
    if 'activated' in data:
        sn = data.get('sn', '')
        if sn:
            migrated = {sn: data}
            _write_all_status(migrated)
            return migrated
        # 无 SN 的异常旧数据，返回空
        return {}

    return data


def _write_all_status(data: dict) -> None:
    """
    写入全量激活状态字典到本地文件（内部辅助函数）。
    """
    path = _get_status_file_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_status(sn: str = None) -> dict:
    """
    读取指定 SN 的激活状态。

    参数：
        sn — SN 码（由 generate_sn() 生成）。为 None 时返回未激活状态。

    返回：
        该 SN 对应的状态 dict，未找到或 sn 为 None 时返回 {'activated': False}。
    """
    if not sn:
        return {'activated': False}

    all_data = _read_all_status()
    return all_data.get(sn, {'activated': False})


def write_status(sn: str, status: dict) -> None:
    """
    将指定 SN 的激活状态写入本地文件。

    读取全量字典 → 合并 dict[sn] = status → 写回。
    不影响其他 SN 的记录。
    """
    all_data = _read_all_status()
    all_data[sn] = status
    _write_all_status(all_data)


def check_activated(username: str = None):
    """
    检查当前用户是否已激活（含过期判断）。

    通过 generate_sn(username) 查询字典，天然实现账号绑定校验
    ——不同用户的 SN 不同，查到的记录自然不同。

    如果已过期，自动将状态标记为未激活并写回文件。

    参数：
        username — 当前用户名（可选）。传入时按 SN 查询该用户的激活记录。

    返回：
        (is_active: bool, info: dict)

        info 包含该用户的激活状态字典，前端可用其展示 License 信息。
    """
    if not username:
        return False, {'activated': False}

    sn = generate_sn(username)
    status = read_status(sn)

    if not status.get('activated'):
        return False, status

    # 检查是否过期
    exp = status.get('exp')
    if exp is not None:
        try:
            exp_date = datetime.strptime(exp[:10], '%Y-%m-%d')
            if datetime.now() > exp_date:
                # 自动标记为未激活
                status['activated'] = False
                write_status(sn, status)
                return False, status
        except ValueError:
            pass

    return True, status


def activate(sn: str, license_str: str, payload: dict) -> dict:
    """
    执行激活操作：验证通过后按 SN 写入状态文件。

    支持重复激活：同一 SN 再次激活时，覆盖之前的记录。
    不影响其他 SN 的激活记录（多用户并行保留）。

    参数：
        sn          — 当前用户的 SN 码（用于校验 License 是否匹配 + 存储 key）
        license_str — 原始 License 字符串（存储备查）
        payload     — verify_license() 返回的 payload dict

    返回激活后的完整状态 dict。
    """
    status = {
        'activated': True,
        'sn': sn,
        'type': payload.get('type', ''),
        'exp': payload.get('exp'),
        'activated_at': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'license': license_str,
    }
    write_status(sn, status)
    return status
