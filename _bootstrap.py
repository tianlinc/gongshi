#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gongshi 更新引导程序（bootstrap launcher / INSPUR-102）

独立可执行文件，负责在应用启动前执行原子化更新操作。
编译为 PyInstaller onefile exe（bootstrap.exe），与主应用同目录。

工作流程：
  1. 检查 %APPDATA%/gongshi/update_ready.json 是否存在
  2. 不存在 → 直接启动主应用 IEI Timer Faster.exe
  3. 存在 → 执行 staging 目录到 app 根目录的原子替换：
     a. 创建 rollback 备份
     b. 复制 added_files
     c. 覆盖 changed_files（含 bsdiff .patch 可选支持）
     d. 删除 removed.list 中的文件
     e. 写入新 VERSION 文件
     f. 清理 staging 目录和 update_ready.json
  4. 替换完成后启动 Python 运行时（IEI Timer Faster.exe）
  5. 失败时从 rollback 目录恢复原文件

命令行参数：
  --rollback    手动触发回滚到上一个版本（从 rollback/ 恢复）
  --help        显示帮助信息
"""

import os
import sys
import json
import shutil
import time
import subprocess
import hashlib
import zipfile
import traceback

# -------------------------------------------------------------------------
# 路径常量
# -------------------------------------------------------------------------

BOOTSTRAP_DIR = os.path.dirname(os.path.abspath(sys.executable)) \
    if getattr(sys, 'frozen', False) \
    else os.path.dirname(os.path.abspath(__file__))

if sys.platform == 'win32':
    DATA_DIR = os.path.join(
        os.environ.get('APPDATA', os.path.expanduser('~')),
        'gongshi'
    )
else:
    DATA_DIR = os.path.join(
        os.path.expanduser('~'), 'Library', 'Application Support', 'gongshi'
    )

APP_EXE_NAME = 'IEI Timer Faster.exe'
UPDATE_READY_FILE = os.path.join(DATA_DIR, 'update_ready.json')
STAGING_DIR_DEFAULT = os.path.join(DATA_DIR, 'staging')
ROLLBACK_DIR = os.path.join(DATA_DIR, 'rollback')
VERSION_FILE = os.path.join(BOOTSTRAP_DIR, 'VERSION')
_LOG_FILE = os.path.join(DATA_DIR, 'bootstrap.log')


# -------------------------------------------------------------------------
# 日志
# -------------------------------------------------------------------------

def _log(msg):
    """追加日志到 bootstrap.log，同时打印到 stderr（调试用）。"""
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    try:
        with open(_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    print(line, file=sys.stderr)


# -------------------------------------------------------------------------
# 工具函数
# -------------------------------------------------------------------------

def _sha256_file(filepath):
    """计算文件的 SHA256 哈希。"""
    h = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _safe_copy(src, dst, retries=5, delay=1.0):
    """带重试的安全文件复制（处理 Windows 文件锁）。

    覆盖已存在的 dst 文件，失败时等待并重试。
    """
    for attempt in range(retries):
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            return True
        except PermissionError:
            if attempt < retries - 1:
                _log(f'[!] 文件被占用, {delay}s后重试 ({attempt+2}/{retries}): {dst}')
                time.sleep(delay)
            else:
                raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
    return False


def _safe_delete(filepath, retries=5, delay=1.0):
    """带重试的安全文件删除。"""
    if not os.path.exists(filepath):
        return True
    for attempt in range(retries):
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
            elif os.path.isdir(filepath):
                shutil.rmtree(filepath)
            return True
        except PermissionError:
            if attempt < retries - 1:
                _log(f'[!] 删除失败(占用), {delay}s后重试 ({attempt+2}/{retries}): {filepath}')
                time.sleep(delay)
            else:
                raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise
    return False


def _kill_app_process():
    """强制终止旧应用进程（确保文件锁释放）。"""
    import subprocess as sp
    try:
        sp.run(
            ['taskkill', '/f', '/im', APP_EXE_NAME],
            capture_output=True,
            timeout=10
        )
        _log('[OK] 已终止旧应用进程')
        time.sleep(2)  # 等待文件锁释放
    except Exception as e:
        _log(f'[!] 终止进程失败（可能未运行）: {e}')


# -------------------------------------------------------------------------
# 回滚备份
# -------------------------------------------------------------------------

def _backup_for_rollback(changed_files, added_files):
    """在替换文件前，将原文件备份到 rollback/ 目录。

    Parameters
    ----------
    changed_files : list of str
        将被覆盖的文件列表（相对于 app 根目录）
    added_files : list of str
        将被新增的文件列表（备份不存在状态，用于回滚时删除）
    """
    os.makedirs(ROLLBACK_DIR, exist_ok=True)

    # 备份元信息
    manifest = {
        'changed_files': {},
        'added_files': [],
        'original_version': None,
    }

    # 读取当前版本号
    if os.path.isfile(VERSION_FILE):
        try:
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                manifest['original_version'] = f.read().strip()
        except Exception:
            pass

    # 备份将被覆盖的文件
    for fname in changed_files:
        src = os.path.join(BOOTSTRAP_DIR, fname)
        backup_name = fname.replace('\\', '_').replace('/', '_')
        backup_path = os.path.join(ROLLBACK_DIR, backup_name)
        if os.path.isfile(src):
            try:
                shutil.copy2(src, backup_path)
                manifest['changed_files'][fname] = backup_name
                _log(f'[OK] 已备份: {fname}')
            except Exception as e:
                _log(f'[!] 备份失败: {fname} - {e}')

    manifest['added_files'] = list(added_files)

    # 保存回滚清单
    rollback_manifest_path = os.path.join(ROLLBACK_DIR, 'rollback_manifest.json')
    try:
        with open(rollback_manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        _log('[OK] 回滚清单已保存')
    except Exception as e:
        _log(f'[!] 回滚清单保存失败: {e}')


def _restore_from_rollback():
    """从 rollback/ 目录恢复原文件。

    Returns
    -------
    bool
        恢复成功返回 True，失败返回 False
    """
    rollback_manifest_path = os.path.join(ROLLBACK_DIR, 'rollback_manifest.json')
    if not os.path.isfile(rollback_manifest_path):
        _log('[!] 未找到回滚清单，无法恢复')
        return False

    try:
        with open(rollback_manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        _log(f'[!] 回滚清单读取失败: {e}')
        return False

    _log('[OK] 开始回滚操作...')

    # 恢复被修改的文件
    changed = manifest.get('changed_files', {})
    for fname, backup_name in changed.items():
        backup_path = os.path.join(ROLLBACK_DIR, backup_name)
        dst = os.path.join(BOOTSTRAP_DIR, fname)
        if os.path.isfile(backup_path):
            try:
                _safe_copy(backup_path, dst)
                _log(f'[OK] 已恢复: {fname}')
            except Exception as e:
                _log(f'[X] 恢复失败: {fname} - {e}')

    # 删除新增的文件（回滚时不应存在）
    added = manifest.get('added_files', [])
    for fname in added:
        dst = os.path.join(BOOTSTRAP_DIR, fname)
        if os.path.exists(dst):
            try:
                os.remove(dst)
                _log(f'[OK] 已删除新增文件: {fname}')
            except Exception as e:
                _log(f'[!] 删除新增文件失败: {fname} - {e}')

    # 恢复版本号
    orig_version = manifest.get('original_version')
    if orig_version:
        try:
            with open(VERSION_FILE, 'w', encoding='utf-8') as f:
                f.write(orig_version)
            _log(f'[OK] 版本号已回滚至: {orig_version}')
        except Exception as e:
            _log(f'[!] 版本号回滚失败: {e}')

    # 清理回滚目录
    try:
        shutil.rmtree(ROLLBACK_DIR)
        _log('[OK] 回滚目录已清理')
    except Exception as e:
        _log(f'[!] 回滚目录清理失败: {e}')

    _log('[OK] 回滚完成')
    return True


# -------------------------------------------------------------------------
# bsdiff 差分补丁（可选）
# -------------------------------------------------------------------------

def _apply_bsdiff_patch(original_file, patch_file, output_file):
    """对大于 5MB 的 changed_files 尝试应用 bsdiff 差分补丁。

    Parameters
    ----------
    original_file : str
        原始文件路径
    patch_file : str
        .patch 差分文件路径
    output_file : str
        输出文件路径

    Returns
    -------
    bool
        补丁应用成功返回 True，失败或 bsdiff4 不可用返回 False
    """
    try:
        import bsdiff4
        with open(original_file, 'rb') as f_orig:
            with open(patch_file, 'rb') as f_patch:
                with open(output_file, 'wb') as f_out:
                    bsdiff4.patch(f_orig.read(), f_patch.read(), f_out)
        return True
    except ImportError:
        _log('[!] bsdiff4 不可用，跳过差分补丁（使用完整文件覆盖）')
        return False
    except Exception as e:
        _log(f'[!] bsdiff 补丁应用失败: {e}')
        return False


# -------------------------------------------------------------------------
# 核心：应用 staging 更新
# -------------------------------------------------------------------------

def _apply_staging(update_info):
    """执行 staging 目录到 app 根目录的原子替换。

    流程：
    1. 验证 manifest.json 中的 SHA256 校验和
    2. 创建 rollback 备份
    3. 应用 added_files（复制新文件）
    4. 应用 changed_files（覆盖，支持 bsdiff .patch 可选）
    5. 删除 removed.list 中的文件
    6. 写入新 VERSION
    7. 清理 staging 目录和 update_ready.json

    Parameters
    ----------
    update_info : dict
        update_ready.json 的内容，含 staging_dir 和 target_version

    Returns
    -------
    bool
        成功返回 True，失败返回 False（失败时会自动回滚）
    """
    staging_dir = update_info.get('staging_dir', STAGING_DIR_DEFAULT)
    target_version = update_info.get('target_version', '')
    chain = update_info.get('chain', [])  # 多版本跳跃的中间版本列表

    if not os.path.isdir(staging_dir):
        _log(f'[!] staging 目录不存在: {staging_dir}')
        return False

    manifest_path = os.path.join(staging_dir, 'manifest.json')
    if not os.path.isfile(manifest_path):
        _log('[!] staging 目录中未找到 manifest.json')
        return False

    # 读取 manifest
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        _log(f'[!] manifest.json 解析失败: {e}')
        return False

    _log(f'[OK] 开始应用更新: {manifest.get("from_version", "?")} → {manifest.get("to_version", target_version)}')

    added_files = manifest.get('added_files', [])
    changed_files = manifest.get('changed_files', [])
    removed_files = manifest.get('removed_files', [])
    expected_sha256 = manifest.get('sha256', {})

    # 0. 校验 SHA256（如果 manifest 中提供了哈希）
    if expected_sha256:
        _log('[OK] 校验文件完整性...')
        all_valid = True
        for fname in added_files + changed_files:
            src = os.path.join(staging_dir, 'files', fname)
            expected = expected_sha256.get(fname)
            if expected and os.path.isfile(src):
                actual = _sha256_file(src)
                if actual != expected:
                    _log(f'[X] SHA256 校验失败: {fname} (期望 {expected}, 实际 {actual})')
                    all_valid = False
                else:
                    _log(f'[OK] SHA256 通过: {fname}')
        if not all_valid:
            _log('[X] 文件完整性校验失败，中止更新')
            return False

    # 1. 创建 rollback 备份
    _log('[OK] 创建回滚备份...')
    _backup_for_rollback(changed_files, added_files)

    # 2. 应用 added_files
    _log('[OK] 复制新增文件...')
    for fname in added_files:
        src = os.path.join(staging_dir, 'files', fname)
        dst = os.path.join(BOOTSTRAP_DIR, fname)
        if os.path.isfile(src):
            try:
                _safe_copy(src, dst)
                _log(f'[OK] 新增: {fname}')
            except Exception as e:
                _log(f'[X] 新增文件失败: {fname} - {e}')
                _log('[X] 开始回滚...')
                _restore_from_rollback()
                return False
        else:
            _log(f'[!] 源文件不存在: {src}')

    # 3. 应用 changed_files（含 bsdiff 可选）
    _log('[OK] 覆盖变更文件...')
    for fname in changed_files:
        src = os.path.join(staging_dir, 'files', fname)
        dst = os.path.join(BOOTSTRAP_DIR, fname)
        patch_src = os.path.join(staging_dir, 'files', fname + '.patch')

        if not os.path.isfile(src):
            _log(f'[!] 变更文件不存在: {src}')
            continue

        try:
            # bsdiff4 可选：文件 > 5MB 且有 .patch 文件时尝试差分补丁
            if os.path.isfile(patch_src) and os.path.isfile(dst):
                src_size = os.path.getsize(src)
                if src_size > 5 * 1024 * 1024:
                    if _apply_bsdiff_patch(dst, patch_src, dst):
                        _log(f'[OK] bsdiff补丁: {fname} ({src_size/1048576:.1f}MB)')
                        continue
            # 否则直接覆盖
            _safe_copy(src, dst)
            _log(f'[OK] 覆盖: {fname}')
        except Exception as e:
            _log(f'[X] 覆盖文件失败: {fname} - {e}')
            _log('[X] 开始回滚...')
            _restore_from_rollback()
            return False

    # 4. 删除 removed_files
    _log('[OK] 删除废弃文件...')
    for fname in removed_files:
        dst = os.path.join(BOOTSTRAP_DIR, fname)
        if os.path.exists(dst):
            try:
                _safe_delete(dst)
                _log(f'[OK] 已删除: {fname}')
            except Exception as e:
                _log(f'[!] 删除文件失败: {fname} - {e}')
        else:
            _log(f'[OK] 已不存在,跳过: {fname}')

    # 5. 写入新版本号
    try:
        with open(VERSION_FILE, 'w', encoding='utf-8') as f:
            f.write(target_version)
        _log(f'[OK] 版本号已更新: {target_version}')
    except Exception as e:
        _log(f'[X] 版本号更新失败: {e}')
        _restore_from_rollback()
        return False

    # 6. 清理 staging 目录和 update_ready.json
    _log('[OK] 清理更新临时文件...')
    try:
        shutil.rmtree(staging_dir)
        _log(f'[OK] staging 目录已清理: {staging_dir}')
    except Exception as e:
        _log(f'[!] staging 目录清理失败: {e}')

    try:
        os.remove(UPDATE_READY_FILE)
        _log('[OK] update_ready.json 已删除')
    except Exception as e:
        _log(f'[!] update_ready.json 删除失败: {e}')

    # 清理 rollback 目录（更新成功，无需保留）
    try:
        if os.path.isdir(ROLLBACK_DIR):
            shutil.rmtree(ROLLBACK_DIR)
            _log('[OK] 回滚目录已清理')
    except Exception:
        pass

    _log(f'[OK] === 更新完成: {target_version} ===')
    return True


# -------------------------------------------------------------------------
# 主入口
# -------------------------------------------------------------------------

def _find_main_app():
    """定位主应用可执行文件。

    在 BOOTSTRAP_DIR（bootstrap.exe 所在目录）下查找 APP_EXE_NAME。
    Returns str or None
    """
    candidate = os.path.join(BOOTSTRAP_DIR, APP_EXE_NAME)
    if os.path.isfile(candidate):
        return candidate
    return None


def launch_main_app():
    """启动主应用（IEI Timer Faster.exe）。

    使用 subprocess.Popen 以 CREATE_NO_WINDOW 启动，
    不等待子进程退出——bootstrap 在这里直接退出。
    """
    app_path = _find_main_app()
    if not app_path:
        _log(f'[X] 未找到主应用: {APP_EXE_NAME} 在 {BOOTSTRAP_DIR}')
        sys.exit(1)

    _log(f'[OK] 启动主应用: {app_path}')
    try:
        if sys.platform == 'win32':
            # 使用 CREATE_NO_WINDOW 防止控制台窗口，让子进程自行管理 GUI 窗口
            subprocess.Popen(
                [app_path],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            subprocess.Popen([app_path])
    except Exception as e:
        _log(f'[X] 启动主应用失败: {e}')
        sys.exit(1)


def main():
    """bootstrap 主流程。

    1. 处理 --rollback 参数
    2. 检查 update_ready.json
    3. 应用 staging 更新（如果存在）
    4. 启动主应用
    """

    # --rollback 手动回滚
    if '--rollback' in sys.argv:
        _log('[OK] 手动回滚模式')
        if _restore_from_rollback():
            # 回滚成功后清理 update_ready（如果存在）
            if os.path.isfile(UPDATE_READY_FILE):
                try:
                    os.remove(UPDATE_READY_FILE)
                    _log('[OK] update_ready.json 已清理')
                except Exception:
                    pass
            print('[OK] 回滚成功，即将启动应用...')
        else:
            print('[X] 回滚失败')
            sys.exit(1)
        launch_main_app()
        return

    # --help
    if '--help' in sys.argv or '-h' in sys.argv:
        print("""gongshi 更新引导程序

用法:
  bootstrap.exe             正常启动（检查更新后启动主应用）
  bootstrap.exe --rollback  手动回滚到上一个版本
  bootstrap.exe --help      显示此帮助信息

工作目录:
  主应用:   %LOCALAPPDATA%/IEI Timer Faster/IEI Timer Faster.exe
  用户数据: %APPDATA%/gongshi/
  更新临时: %APPDATA%/gongshi/staging/
  回滚备份: %APPDATA%/gongshi/rollback/""")
        return

    _log('[OK] === gongshi bootstrap 启动 ===')
    _log(f'[OK] bootstrap 目录: {BOOTSTRAP_DIR}')
    _log(f'[OK] 用户数据目录: {DATA_DIR}')

    # 检查是否有待应用的更新
    if os.path.isfile(UPDATE_READY_FILE):
        _log('[OK] 检测到 update_ready.json，开始应用更新...')
        try:
            with open(UPDATE_READY_FILE, 'r', encoding='utf-8') as f:
                update_info = json.load(f)
        except Exception as e:
            _log(f'[X] update_ready.json 读取失败: {e}')
            # 损坏的文件，删除后继续启动
            try:
                os.remove(UPDATE_READY_FILE)
            except Exception:
                pass
            launch_main_app()
            return

        # 关闭旧应用进程（确保文件锁释放）
        _kill_app_process()

        # 应用更新
        if _apply_staging(update_info):
            _log('[OK] 更新应用成功')
        else:
            _log('[X] 更新应用失败，尝试回滚...')
            _restore_from_rollback()

    # 启动主应用
    launch_main_app()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        _log(f'[X] bootstrap 致命错误: {e}')
        _log(traceback.format_exc())
        # 即使出错也尝试启动主应用（优雅降级）
        try:
            launch_main_app()
        except Exception:
            pass
        sys.exit(1)
