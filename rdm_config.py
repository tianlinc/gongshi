# -*- coding: utf-8 -*-
"""
RDM 地址配置模块 — 文件持久化存储

参照 license_utils.py 的设计模式：
  - 开发模式：rdm_config.json 存放在项目根目录
  - 打包模式（sys.frozen）：存放在 %APPDATA%/gongshi/rdm_config.json

默认 RDM 地址：http://10.111.36.3:2029
"""

import os
import json

DEFAULT_RDM_URL = 'http://10.111.36.3:2029'


def _get_config_file_path() -> str:
    """
    获取 rdm_config.json 的完整路径。

    - PyInstaller 打包模式（sys.frozen）：
        Windows: %APPDATA%/gongshi/rdm_config.json
        macOS:   ~/Library/Application Support/gongshi/rdm_config.json
        其他:    ~/gongshi/rdm_config.json
    - 开发模式：与 rdm_config.py 同目录（项目根目录）。
    """
    import sys
    if getattr(sys, 'frozen', False):
        if sys.platform == 'darwin':
            data_dir = os.path.join(
                os.path.expanduser('~'), 'Library', 'Application Support', 'gongshi')
        elif sys.platform == 'win32':
            appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
            data_dir = os.path.join(appdata, 'gongshi')
        else:
            data_dir = os.path.join(os.path.expanduser('~'), 'gongshi')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'rdm_config.json')
    # 开发模式 → 与 rdm_config.py 同目录
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'rdm_config.json'
    )


def _read_config() -> dict:
    """读取全量配置，文件不存在时返回空 dict。"""
    path = _get_config_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, Exception):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_config(data: dict) -> None:
    """写入全量配置到文件。"""
    path = _get_config_file_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_rdm_base_url() -> str:
    """
    获取 RDM 服务器地址。

    优先级：
      1. 文件配置（rdm_config.json 中的 url 字段）
      2. 默认地址（DEFAULT_RDM_URL）
    """
    config = _read_config()
    url = config.get('url', '').strip()
    if url:
        return url
    return DEFAULT_RDM_URL


def set_rdm_base_url(url: str) -> None:
    """
    保存 RDM 服务器地址到配置文件。

    参数：
        url — RDM 服务器地址（如 http://10.111.36.3:2029）
    """
    config = _read_config()
    config['url'] = url.strip()
    config['updated_at'] = __import__('datetime').datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    _write_config(config)


def reset_rdm_base_url() -> str:
    """
    恢复默认 RDM 地址，写入文件并返回。
    """
    set_rdm_base_url(DEFAULT_RDM_URL)
    return DEFAULT_RDM_URL
