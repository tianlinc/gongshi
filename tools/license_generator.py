# -*- coding: utf-8 -*-
"""
License 生成工具 — 独立运行，供管理员根据客户 SN 码签发 License。

用法：
    python tools/license_generator.py

交互式输入：
    1. 粘贴客户的 SN 码
    2. 选择时长类型（1年 / 永久）
    3. 输出 License 字符串

与 Web 端使用相同的 license_utils 模块，确保算法一致。

依赖：
    - 仅需 Python 标准库（hmac, hashlib, base64, json 等），无需额外安装
    - 与 app.py 不耦合，可独立运行

密钥：
    - 读取环境变量 RDM_SECRET_KEY，未设置时使用默认开发密钥
    - 换密钥后需重新签发所有 License
"""

import os
import sys

# 将项目根目录加入 sys.path，以便 import license_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from license_utils import generate_sn, generate_license, verify_license


def main():
    print("=" * 50)
    print("  License 生成工具")
    print("=" * 50)
    print()
    print("根据客户的 SN 码生成 License 字符串。")
    print("密钥来源：RDM_SECRET_KEY 环境变量（未设置则使用默认开发密钥）")
    print()

    # ---- 输入 SN ----
    while True:
        sn = input("请输入客户的 SN 码: ").strip()
        if sn:
            break
        print("[X] SN 码不能为空，请重新输入")

    # ---- 选择时长 ----
    print()
    print("请选择授权时长：")
    print("  1 — 1 年")
    print("  2 — 永久")
    while True:
        choice = input("请输入选项 (1/2): ").strip()
        if choice == '1':
            duration = '1年'
            break
        elif choice == '2':
            duration = '永久'
            break
        else:
            print("[X] 无效选项，请输入 1 或 2")

    # ---- 生成 License ----
    print()
    print("正在生成 License...")
    try:
        license_str = generate_license(sn, duration)
    except ValueError as e:
        print(f"[X] 生成失败: {e}")
        return

    print()
    print("=" * 50)
    print("  License 已生成")
    print("=" * 50)
    print()
    print(f"  SN:       {sn}")
    print(f"  时长:     {duration}")
    print(f"  License:  {license_str}")
    print()
    print("请将 License 字符串复制给客户，在激活页面输入即可。")
    print()

    # ---- 自验证（确保生成结果能通过验证） ----
    valid, payload, error = verify_license(license_str)
    if valid:
        print(f"[OK] 自验证通过 "
              f"sn={payload.get('sn')} type={payload.get('type')} "
              f"exp={payload.get('exp')}")
    else:
        print(f"[X] 自验证失败: {error}")
        print("[X] 请检查密钥配置是否正确（生成和验证必须使用相同密钥）")

    print()


if __name__ == '__main__':
    main()
