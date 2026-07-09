#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEI Timer Faster 桌面版启动器

INSPUR-74: 从 Windows 后台服务（NSSM）改造为独立桌面应用。
用户双击快捷方式即可在 WebView2 窗口中访问，无需系统浏览器。

特性:
  - 端口冲突自动递增（5000 → 5001 → 5002）
  - 仅 WebView2（无 CEF 后端）
  - 共享逻辑提取到 _desktop_common.py

开发模式（未打包）：
    python service_launcher.py         # debug=True + webbrowser（调试用）

打包模式（PyInstaller）：
    IEI Timer Faster.exe               # debug=False + pywebview 独立桌面窗口
"""

import os
import sys

# 确保项目根目录可导入 _desktop_common（dev 模式需要）
if not getattr(sys, 'frozen', False):
    _proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _proj_root not in sys.path:
        sys.path.insert(0, _proj_root)

from _desktop_common import DesktopLauncher


def main():
    DesktopLauncher(port=5000, port_auto=True, enable_cef=False).run()


if __name__ == '__main__':
    main()
