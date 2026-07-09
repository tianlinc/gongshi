#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INSPUR-73: 对比 HTTP 版 get_my_tasks_http() 与 Playwright 版 get_my_tasks() 的结果。

用法（需设 RDM_USER / RDM_PASS 环境变量）：
    python tools/test_http_vs_playwright.py
"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import RDMClient, USE_HTTP_TASKS


def main():
    username = os.environ.get('RDM_USER', '').strip()
    password = os.environ.get('RDM_PASS', '').strip()
    if not username or not password:
        print("[X] 请设置 RDM_USER 和 RDM_PASS 环境变量")
        sys.exit(1)

    client = RDMClient(username, password)
    login_result = client.login()
    if not login_result.get('success'):
        print(f"[X] 登录失败: {login_result.get('message')}")
        sys.exit(1)
    print(f"[OK] 登录成功 user={username}")

    # ----- HTTP 版 -----
    print("\n=== HTTP 版 (get_my_tasks_http) ===")
    start = datetime.now()
    try:
        http_tasks = client.get_my_tasks_http()
        http_ok = True
    except Exception as e:
        print(f"[X] HTTP 版失败: {e}")
        http_tasks = []
        http_ok = False
    http_time = (datetime.now() - start).total_seconds()
    print(f"[OK] HTTP 版耗时 {http_time:.1f}s 返回 {len(http_tasks)} 条任务")

    # ----- Playwright 版 -----
    print("\n=== Playwright 版 (get_my_tasks) ===")
    start = datetime.now()
    try:
        pw_tasks = client.get_my_tasks()
        pw_ok = True
    except Exception as e:
        print(f"[X] Playwright 版失败: {e}")
        pw_tasks = []
        pw_ok = False
    pw_time = (datetime.now() - start).total_seconds()
    print(f"[OK] Playwright 版耗时 {pw_time:.1f}s 返回 {len(pw_tasks)} 条任务")

    # ----- 对比 -----
    print(f"\n=== 对比结果 ===")

    if http_ok and pw_ok:
        http_ids = {t['task_id'] for t in http_tasks}
        pw_ids = {t['task_id'] for t in pw_tasks}

        http_only = http_ids - pw_ids
        pw_only = pw_ids - http_ids
        common = http_ids & pw_ids

        print(f"  共同任务: {len(common)}")
        print(f"  仅 HTTP 版: {len(http_only)}  {http_only}")
        print(f"  仅 Playwright 版: {len(pw_only)}  {pw_only}")

        # 逐字段对比
        mismatches = 0
        for hid in common:
            ht = next(t for t in http_tasks if t['task_id'] == hid)
            pt = next(t for t in pw_tasks if t['task_id'] == hid)
            for key in ['name', 'project', 'project_id', 'status_code',
                        'plan_start', 'plan_end', 'status']:
                hv = ht.get(key, '')
                pv = pt.get(key, '')
                if hv != pv:
                    mismatches += 1
                    print(f"  [X] 字段不一致 task={hid} field={key}: "
                          f"HTTP='{hv}' vs PW='{pv}'")
        if mismatches == 0:
            print("  [OK] 所有共同任务字段完全一致")
        else:
            print(f"  [X] 共 {mismatches} 处不一致")

        print(f"\n  性能对比: HTTP {http_time:.1f}s vs Playwright {pw_time:.1f}s")
        if pw_time > 0:
            speedup = pw_time / max(http_time, 0.001)
            print(f"  HTTP 版快 {speedup:.1f}x")
    else:
        if not http_ok:
            print("  [X] HTTP 版执行失败，无法对比")
        if not pw_ok:
            print("  [X] Playwright 版执行失败，无法对比")

    # 输出 HTTP 版任务列表
    print(f"\n=== HTTP 版任务列表 ({len(http_tasks)} 条) ===")
    for t in http_tasks:
        print(f"  [{t['status_code']}] {t['task_id'][:8]}... "
              f"{t['name'][:50]} | {t['project'][:30]}")


if __name__ == '__main__':
    main()
