# -*- coding: utf-8 -*-
"""
INSPUR-56 / INSPUR-57 License 模块测试脚本
测试用例 TC1 ~ TC5

用法：
    python test_license_inspur56.py
"""

import os
import sys
import json
from datetime import datetime, timedelta

# 确保能 import license_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from license_utils import (
    generate_sn,
    generate_license,
    verify_license,
    read_status,
    write_status,
    activate,
    check_activated,
    _read_all_status,
    _write_all_status,
    _get_status_file_path,
)

PASS = "[OK]"
FAIL = "[X]"
results = {}


def test_case(name, fn):
    """运行测试用例，记录结果。"""
    print(f"\n{'='*60}")
    print(f"  TC: {name}")
    print(f"{'='*60}")
    try:
        fn()
        results[name] = "PASS"
        print(f"\n{PASS} {name} — 通过")
    except AssertionError as e:
        results[name] = "FAIL"
        print(f"\n{FAIL} {name} — 不通过: {e}")
    except Exception as e:
        results[name] = "ERROR"
        print(f"\n{FAIL} {name} — 异常: {e}")


def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}\n    预期: {expected!r}\n    实际: {actual!r}")


def assert_true(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "条件为 False")


def reset_status_file():
    """清空 license_status.json。"""
    _write_all_status({})


# ===========================================================================
# TC1: 多用户各自激活，记录独立保留
# ===========================================================================

def tc1_multi_user():
    user_a = "testuser_a_inspur56"
    user_b = "testuser_b_inspur56"
    sn_a = generate_sn(user_a)
    sn_b = generate_sn(user_b)

    reset_status_file()

    # Step 1: 用户 A 激活
    print(f"  Step 1: 用户 A ({user_a}) → SN={sn_a}")
    lic_a = generate_license(sn_a, "1年")
    valid, payload, err = verify_license(lic_a)
    assert_true(valid, f"License A 验证失败: {err}")
    activate(sn_a, lic_a, payload)
    print(f"    激活成功，License type={payload['type']}")

    # Step 2: 检查 license_status.json 有 A 的记录
    print(f"  Step 2: 检查文件中有 A 的记录")
    all_data = _read_all_status()
    assert_true(sn_a in all_data, f"文件中找不到 A 的 SN ({sn_a})")
    assert_true(all_data[sn_a].get('activated'), "A 的 activated 应为 True")
    print(f"    文件中 keys: {list(all_data.keys())}")

    # Step 3: 用户 B 激活
    print(f"  Step 3: 用户 B ({user_b}) → SN={sn_b}")
    lic_b = generate_license(sn_b, "永久")
    valid, payload, err = verify_license(lic_b)
    assert_true(valid, f"License B 验证失败: {err}")
    activate(sn_b, lic_b, payload)
    print(f"    激活成功，License type={payload['type']}")

    # Step 4: 检查两条记录并存
    print(f"  Step 4: 检查 A 和 B 两条记录并存")
    all_data = _read_all_status()
    assert_true(sn_a in all_data, "A 的记录丢失!")
    assert_true(sn_b in all_data, "B 的记录丢失!")
    assert_eq(all_data[sn_a]['activated'], True, "A 的 activated 应为 True")
    assert_eq(all_data[sn_b]['activated'], True, "B 的 activated 应为 True")
    assert_eq(all_data[sn_a]['type'], "1年", "A 的 type 不对")
    assert_eq(all_data[sn_b]['type'], "永久", "B 的 type 不对")
    print(f"    文件中 keys: {list(all_data.keys())}")
    print(f"    A: activated={all_data[sn_a]['activated']}, type={all_data[sn_a]['type']}")
    print(f"    B: activated={all_data[sn_b]['activated']}, type={all_data[sn_b]['type']}")

    # Step 5: 用户 A 重新登录 → 应正常通过
    print(f"  Step 5: 用户 A 重新登录 → check_activated 应返回 True")
    is_active, info = check_activated(user_a)
    assert_true(is_active, f"用户 A 应该已激活，但 check_activated 返回 False. info={info}")
    print(f"    check_activated({user_a}) → {is_active}")


# ===========================================================================
# TC2: 重复激活（覆盖旧 License）
# ===========================================================================

def tc2_repeat_activate():
    user = "testuser_tc2"
    sn = generate_sn(user)

    reset_status_file()

    # Step 1: 用户激活第一个 License（1年）
    print(f"  Step 1: 用户 {user} 激活 License #1（1年）")
    lic1 = generate_license(sn, "1年")
    valid, payload1, err = verify_license(lic1)
    assert_true(valid, f"License #1 验证失败: {err}")
    result1 = activate(sn, lic1, payload1)
    print(f"    License #1: type={result1['type']}, exp={result1.get('exp')}")

    # Step 2: 用户用第二个 License（永久）再激活
    print(f"  Step 2: 用户 {user} 激活 License #2（永久）")
    lic2 = generate_license(sn, "永久")
    valid, payload2, err = verify_license(lic2)
    assert_true(valid, f"License #2 验证失败: {err}")
    result2 = activate(sn, lic2, payload2)
    print(f"    License #2: type={result2['type']}, exp={result2.get('exp')}")

    # Step 3: 检查记录被覆盖
    print(f"  Step 3: 检查 A 的记录被新 License 覆盖")
    all_data = _read_all_status()
    assert_true(sn in all_data, "用户记录丢失!")
    record = all_data[sn]
    assert_eq(record['type'], "永久", "type 应为'永久'(新 License 的值)")
    assert_eq(record['exp'], None, "exp 应为 None（永久 License）")
    assert_eq(record['license'], lic2, "license 字段应为新 License 字符串")
    # 确认是 1 条记录，不是 2 条
    assert_eq(len(all_data), 1, f"应该只有 1 条记录，实际有 {len(all_data)} 条")

    # Step 4: 用户登录 → 正常通过
    print(f"  Step 4: 用户 {user} 登录 → check_activated 应返回 True")
    is_active, info = check_activated(user)
    assert_true(is_active, f"重复激活后用户应该能正常登录. info={info}")
    print(f"    check_activated({user}) → {is_active}, type={info.get('type')}")


# ===========================================================================
# TC3: 旧数据自动迁移
# ===========================================================================

def tc3_old_data_migration():
    test_sn = "dGVzdF9zbl90YzM="  # 测试用 SN
    old_data = {
        "activated": True,
        "sn": test_sn,
        "type": "1年",
        "exp": "2027-12-31T00:00:00",
        "activated_at": "2025-01-01T00:00:00",
        "license": "test_old_license_string",
    }

    # Step 1: 备份当前状态
    print(f"  Step 1: 写入旧格式单条记录")
    path = _get_status_file_path()
    _write_all_status(old_data)  # 这会写入旧格式？不对，_write_all_status 只是 json.dump
    # 需要直接写入旧格式（顶层含 activated 键）
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(old_data, f, ensure_ascii=False, indent=2)
    print(f"    写入旧格式: {json.dumps(old_data, ensure_ascii=False)}")

    # Step 2: 验证文件确实是旧格式
    print(f"  Step 2: 确认文件当前是旧格式")
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    assert_true('activated' in raw and raw.get('activated') is True,
                "文件应包含旧格式特征 (activated=true at top level)")
    print(f"    旧格式特征: activated={raw.get('activated')}, sn={raw.get('sn')}")

    # Step 3: 通过 _read_all_status() 读取 → 自动迁移
    print(f"  Step 3: 调用 _read_all_status() → 自动迁移")
    all_data = _read_all_status()
    # 不应再含顶层 activated
    assert_true('activated' not in all_data,
                "迁移后字典顶层不应含 'activated' 键")
    assert_true(test_sn in all_data,
                f"迁移后应包含 sn={test_sn}")
    assert_eq(all_data[test_sn]['activated'], True, "迁移后 activated 应为 True")
    assert_eq(all_data[test_sn]['type'], "1年")
    print(f"    迁移后 keys: {list(all_data.keys())}")
    print(f"    {test_sn}: {all_data[test_sn]}")

    # Step 4: 检查文件也已迁移
    print(f"  Step 4: 重新读取文件，确认已写回新格式")
    with open(path, 'r', encoding='utf-8') as f:
        raw2 = json.load(f)
    assert_true('activated' not in raw2, "文件中不应再含顶层 'activated' 键")
    assert_true(test_sn in raw2, f"文件中应包含 sn={test_sn}")
    print(f"    文件已迁移为新格式 [OK]")


# ===========================================================================
# TC4: 过期 License 拒绝
# ===========================================================================

def tc4_expired_license():
    user = "testuser_tc4"
    sn = generate_sn(user)

    reset_status_file()

    # Step 1: 写入一个已过期的激活记录
    print(f"  Step 1: 写入已过期的激活记录")
    expired_status = {
        "activated": True,
        "sn": sn,
        "type": "1年",
        "exp": "2020-01-01T00:00:00",  # 已过期
        "activated_at": "2019-01-01T00:00:00",
        "license": "expired_license_string",
    }
    write_status(sn, expired_status)
    print(f"    exp={expired_status['exp']} (已过期)")

    # Step 2: 确认写入时 activated=True
    print(f"  Step 2: 确认写入时 activated=True")
    data_before = _read_all_status()
    assert_eq(data_before[sn]['activated'], True, "写入时 activated 应为 True")

    # Step 3: check_activated → 应返回 False
    print(f"  Step 3: check_activated({user}) → 应返回 False（已过期）")
    is_active, info = check_activated(user)
    assert_true(not is_active, f"过期用户应返回 False，实际返回 {is_active}")
    print(f"    check_activated → {is_active} (预期 False)")

    # Step 4: 检查文件中的 activated 被自动改为 False
    print(f"  Step 4: 检查文件中的 activated 被自动标记为 False")
    data_after = _read_all_status()
    assert_eq(data_after[sn]['activated'], False,
              f"过期后 activated 应自动变为 False，实际为 {data_after[sn]['activated']}")
    print(f"    文件中 activated={data_after[sn]['activated']} (自动置为 False) [OK]")


# ===========================================================================
# TC5: 未激活用户访问拦截
# ===========================================================================

def tc5_unactivated_user():
    user = "testuser_never_activated"
    sn = generate_sn(user)

    reset_status_file()

    # Step 1: 确认没有任何激活记录
    print(f"  Step 1: 确认文件中没有 {user} 的激活记录")
    all_data = _read_all_status()
    assert_true(sn not in all_data, f"SN {sn} 不应存在于文件中")

    # Step 2: check_activated 返回 False
    print(f"  Step 2: check_activated({user}) → 应返回 False")
    is_active, info = check_activated(user)
    assert_true(not is_active, f"未激活用户 check_activated 应返回 False，实际返回 {is_active}")
    assert_eq(info.get('activated'), False, "info['activated'] 应为 False")
    print(f"    check_activated → {is_active}, info={info}")


    # Step 3: read_status 也返回未激活
    print(f"  Step 3: read_status({sn}) → 应返回 activated=False")
    status = read_status(sn)
    assert_eq(status.get('activated'), False, "read_status 应返回 activated=False")
    print(f"    read_status → {status}")

    # Step 4: 确认 license_status.json 中没有新增记录
    print(f"  Step 4: 确认 check_activated 没有在文件中创建记录")
    all_data_after = _read_all_status()
    assert_true(sn not in all_data_after,
                f"未激活用户的 check_activated 不应写入文件，但实际存在")
    print(f"    文件为空 = {all_data_after == {}}")


# ===========================================================================
# 主函数
# ===========================================================================

def main():
    print("=" * 60)
    print("  INSPUR-56 / INSPUR-57 License 模块测试")
    print(f"  执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  license_status.json: {_get_status_file_path()}")
    print("=" * 60)

    test_case("TC1: 多用户各自激活，记录独立保留", tc1_multi_user)
    test_case("TC2: 重复激活（覆盖旧 License）", tc2_repeat_activate)
    test_case("TC3: 旧数据自动迁移", tc3_old_data_migration)
    test_case("TC4: 过期 License 拒绝", tc4_expired_license)
    test_case("TC5: 未激活用户访问拦截", tc5_unactivated_user)

    # 汇总
    print(f"\n{'='*60}")
    print(f"  测试汇总")
    print(f"{'='*60}")
    total = len(results)
    passed = sum(1 for v in results.values() if v == "PASS")
    failed = total - passed

    for name, result in results.items():
        icon = PASS if result == "PASS" else FAIL
        print(f"  {icon} {name}")

    print(f"\n  合计: {total} 个用例, {passed} 通过, {failed} 不通过")
    print(f"{'='*60}")

    return failed == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
