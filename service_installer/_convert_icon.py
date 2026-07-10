#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macOS .ico → .icns 图标转换工具。
从 iei_timer.ico 提取最大尺寸的 PNG，用 sips+iconutil 生成 .icns。
"""

import os
import shutil
import struct


def convert():
    if not os.path.exists('iei_timer.ico'):
        print("[!] iei_timer.ico not found")
        return

    with open('iei_timer.ico', 'rb') as f:
        data = f.read()

    count = data[4] | (data[5] << 8)
    best_size, best_offset, best_len = 0, 0, 0

    for i in range(count):
        o = 6 + i * 16
        w, h = data[o], data[o + 1]
        if w == 0:
            w = 256
        if h == 0:
            h = 256
        size = w * h
        if size > best_size:
            best_size = size
            best_offset = (
                data[o + 12]
                | (data[o + 13] << 8)
                | (data[o + 14] << 16)
                | (data[o + 15] << 24)
            )
            best_len = (
                data[o + 8]
                | (data[o + 9] << 8)
                | (data[o + 10] << 16)
                | (data[o + 11] << 24)
            )

    if not best_offset:
        print("[X] No image data found in ICO")
        return

    png = data[best_offset:best_offset + best_len]
    # PNG magic: \x89 P N G \r \n \x1a \n
    png_magic = bytes([0x89, 0x50, 0x4E, 0x47])

    if png[:4] != png_magic:
        print("[X] Extracted data is not PNG")
        return

    with open('iei_timer.png', 'wb') as f:
        f.write(png)

    os.makedirs('tmp.iconset', exist_ok=True)

    for sz in (16, 32, 64, 128, 256, 512):
        os.system(
            'sips -z %d %d iei_timer.png --out tmp.iconset/icon_%dx%d.png 2>/dev/null'
            % (sz, sz, sz, sz)
        )
        if sz <= 256:
            os.system(
                'sips -z %d %d iei_timer.png --out tmp.iconset/icon_%dx%d@2x.png 2>/dev/null'
                % (sz * 2, sz * 2, sz, sz)
            )

    os.system('iconutil -c icns tmp.iconset -o iei_timer.icns 2>/dev/null')
    shutil.rmtree('tmp.iconset', ignore_errors=True)

    print(
        '[OK] icns created' if os.path.exists('iei_timer.icns')
        else '[X] icns creation failed'
    )


if __name__ == '__main__':
    convert()
