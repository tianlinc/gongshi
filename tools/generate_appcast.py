#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 appcast.xml（Sparkle 协议格式）供 macOS 客户端检查更新。

用法:
    python tools/generate_appcast.py                        # 使用 VERSION 文件中的版本
    python tools/generate_appcast.py --version 1.1.0        # 指定版本号
    python tools/generate_appcast.py --version 1.1.0 --dmg-url https://.../Setup.dmg  # 指定 DMG 地址
    python tools/generate_appcast.py --version 1.1.0 --dmg-url <url> --file-size 12345678 --pub-date "Mon, 01 Jan 2026 00:00:00 +0000"

输出:
    appcast.xml 写入当前目录，上传到 GitHub Pages 后可通过 https://tianlinc.github.io/gongshi/appcast.xml 访问。

CI 集成:
    GITHUB_REF 环境变量存在时（如 refs/tags/v1.1.0），自动从 tag 名提取版本号。
    配合 GitHub Releases 时，dmg-url 指向上传的 artifact URL。
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape


SPARKLE_NS = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
BASE_URL = 'https://tianlinc.github.io/gongshi'


def read_version():
    """读取项目根目录 VERSION 文件。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    version_path = os.path.join(base_dir, 'VERSION')
    if os.path.isfile(version_path):
        with open(version_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None


def extract_tag_version():
    """从 CI 环境变量 GITHUB_REF 提取版本号（v1.1.0 → 1.1.0）。"""
    ref = os.environ.get('GITHUB_REF') or os.environ.get('CI_COMMIT_TAG')
    if ref:
        return ref.replace('refs/tags/', '').lstrip('v')
    return None


def build_appcast_xml(version, dmg_url, file_size=None, pub_date=None, notes=None, min_version=None):
    """生成 appcast.xml 内容字符串。"""
    if pub_date is None:
        pub_date = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')

    title = f'Version {version}'
    desc = notes or f'IEI Timer Faster V{version}'

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<rss version="2.0" xmlns:sparkle="{SPARKLE_NS}">',
        '  <channel>',
        '    <title>IEI Timer Faster</title>',
        '    <item>',
        f'      <title>{xml_escape(title)}</title>',
        f'      <description><![CDATA[{desc}]]></description>',
        f'      <pubDate>{pub_date}</pubDate>',
    ]

    enclosure_attrs = [
        f'url="{xml_escape(dmg_url)}"',
        f'sparkle:version="{xml_escape(version)}"',
        f'sparkle:shortVersionString="{xml_escape(version)}"',
        'type="application/x-apple-diskimage"',
    ]
    if file_size:
        enclosure_attrs.append(f'length="{file_size}"')
    if min_version:
        enclosure_attrs.append(f'sparkle:minimumSystemVersion="{xml_escape(min_version)}"')

    lines.append(f'      <enclosure {" ".join(enclosure_attrs)}/>')
    lines.append('    </item>')
    lines.append('  </channel>')
    lines.append('</rss>')

    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(
        description='生成 IEI Timer Faster 的 appcast.xml（Sparkle 格式）'
    )
    parser.add_argument('--version', '-v', help='版本号（如 1.1.0），默认从 VERSION 文件读取')
    parser.add_argument('--dmg-url', '-u', help='DMG 下载地址（默认: {BASE}/releases/latest/download/IEI_Timer_Faster_Setup.dmg）')
    parser.add_argument('--file-size', '-s', type=int, help='DMG 文件大小（字节）')
    parser.add_argument('--pub-date', '-d', help='发布日期（RFC 2822 格式），默认当前 UTC 时间')
    parser.add_argument('--notes', '-n', help='版本更新说明')
    parser.add_argument('--min-version', '-m', help='最低系统版本要求')
    parser.add_argument('--output', '-o', default='appcast.xml', help='输出文件路径（默认: appcast.xml）')

    args = parser.parse_args()

    # 确定版本号 >>> CI tag > --version > VERSION 文件
    version = extract_tag_version() or args.version or read_version()
    if not version:
        print("[X] 未找到版本号。请使用 --version 指定或在项目根目录创建 VERSION 文件。")
        sys.exit(1)

    # 确定 DMG URL
    dmg_url = args.dmg_url or (
        f'{BASE_URL}/releases/latest/download/IEI_Timer_Faster_Setup.dmg'
    )

    xml_content = build_appcast_xml(
        version=version,
        dmg_url=dmg_url,
        file_size=args.file_size,
        pub_date=args.pub_date,
        notes=args.notes,
        min_version=args.min_version,
    )

    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(os.getcwd(), output_path)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    print(f"[OK] appcast.xml 已生成: {output_path}")
    print(f"     版本: {version}")
    print(f"     DMG:  {dmg_url}")


if __name__ == '__main__':
    main()
