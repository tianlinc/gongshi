#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDM 系统探测脚本 - 找到工时填报的实际接口
"""

import sys
import os

# 先安装依赖
print("正在安装依赖...")
os.system("pip install pycryptodome requests beautifulsoup4 -q")

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
import requests
from bs4 import BeautifulSoup
import re
import json


class RDMExplorer:
    """RDM 系统探测器"""

    def __init__(self, base_url="http://10.111.36.3:2029"):
        self.base_url = base_url
        self.session = requests.Session()
        self.aes_key = b"abcdefgabcdefg12"
        self.logged_in = False

    def encrypt(self, text):
        """AES ECB 加密"""
        cipher = AES.new(self.aes_key, AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted).decode('utf-8')

    def login(self, username, password):
        """登录系统"""
        print(f"\n{'='*60}")
        print(f"1. 访问登录页面: {self.base_url}/index.jsp")
        resp = self.session.get(f"{self.base_url}/index.jsp")
        print(f"   状态: {resp.status_code}")

        print(f"\n2. 准备登录数据")
        # Base64 编码后再 AES 加密
        encrypted_username = self.encrypt(base64.b64encode(username.encode('utf-8')).decode('utf-8'))
        encrypted_password = self.encrypt(base64.b64encode(password.encode('utf-8')).decode('utf-8'))

        login_data = {
            "j_username": encrypted_username,
            "j_password": encrypted_password,
            "isExpires": "1",
            "sessionIndex": "",
            "BROWSER_VERSION": "1",
            "REMOTE_LANGUAGE": "zh-cn"
        }

        auth_url = f"{self.base_url}/j_security_check"
        print(f"\n3. 提交登录: {auth_url}")
        resp = self.session.post(auth_url, data=login_data, allow_redirects=True)

        print(f"   最终URL: {resp.url}")
        print(f"   响应长度: {len(resp.text)}")

        if "error=true" in resp.url:
            print("\n[X] 登录失败：用户名或密码错误")
            return False

        if "loginForm" in resp.text and len(resp.text) < 15000:
            print("\n[X] 登录失败：仍在登录页面")
            return False

        print("\n[OK] 登录成功！")
        self.logged_in = True
        return True

    def find_task_menu(self):
        """查找任务菜单"""
        if not self.logged_in:
            print("请先登录")
            return

        print(f"\n{'='*60}")
        print("4. 查找任务菜单...")
        print(f"{'='*60}")

        # 访问主页
        resp = self.session.get(f"{self.base_url}/main.do")
        print(f"\n主页内容长度: {len(resp.text)}")

        # 保存主页内容
        with open('main_page.html', 'w', encoding='utf-8') as f:
            f.write(resp.text)
        print("已保存主页到: main_page.html")

        # 解析菜单
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 查找包含"任务"关键词的链接
        print("\n查找包含'任务'的链接:")
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True)
            href = link.get('href')
            if '任务' in text or 'task' in text.lower():
                print(f"  [OK] {text} -> {href}")

        # 查找包含"工时"关键词的链接
        print("\n查找包含'工时/考勤/填报'的链接:")
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True)
            href = link.get('href')
            if any(kw in text for kw in ['工时', '考勤', '填报', 'timesheet', 'worklog', 'attendance']):
                print(f"  [OK] {text} -> {href}")

    def try_task_pages(self):
        """尝试访问任务页面"""
        if not self.logged_in:
            return

        print(f"\n{'='*60}")
        print("5. 尝试常见任务/工时页面...")
        print(f"{'='*60}")

        possible_urls = [
            # 任务相关
            "/task.do",
            "/task/myTask.do",
            "/task/myTasks.do",
            "/task/list.do",
            "/task/myTaskList.do",
            "/myTask.do",
            "/mytask.do",

            # 工时相关
            "/timesheet.do",
            "/timesheet/input.do",
            "/timesheet/main.do",
            "/worklog.do",
            "/worklog/input.do",

            # 考勤相关
            "/attendance.do",
            "/attendance/input.do",
            "/worktime.do",
        ]

        found_pages = []

        for url_path in possible_urls:
            full_url = self.base_url + url_path
            try:
                print(f"\n尝试: {url_path}")
                resp = self.session.get(full_url, timeout=5)

                if resp.status_code == 200 and len(resp.text) > 1000:
                    # 检查页面内容
                    has_task = '任务' in resp.text or 'task' in resp.text.lower()
                    has_timesheet = '工时' in resp.text or 'timesheet' in resp.text.lower()

                    if has_task or has_timesheet:
                        # 保存页面
                        filename = url_path.replace('/', '_').strip('_') + '.html'
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(resp.text)

                        print(f"  [OK] 成功！包含: {'任务 ' if has_task else ''}{'工时 ' if has_timesheet else ''}")
                        print(f"  已保存到: {filename}")
                        found_pages.append((url_path, filename))
                    else:
                        print(f"  响应正常但无关键词")
                else:
                    print(f"  [X] 状态码: {resp.status_code}, 长度: {len(resp.text)}")

            except Exception as e:
                print(f"  [X] 错误: {str(e)[:50]}")

        return found_pages

    def analyze_iframes(self):
        """分析 iframe 框架"""
        if not self.logged_in:
            return

        print(f"\n{'='*60}")
        print("6. 分析 iframe 框架...")
        print(f"{'='*60}")

        with open('main_page.html', 'r', encoding='utf-8') as f:
            content = f.read()

        soup = BeautifulSoup(content, 'html.parser')

        # 查找所有 frame
        frames = soup.find_all(['iframe', 'frame'])
        if frames:
            print(f"\n找到 {len(frames)} 个 frame:")
            for i, frame in enumerate(frames, 1):
                src = frame.get('src', '')
                name = frame.get('name', frame.get('id', ''))
                print(f"  {i}. name/id: {name}, src: {src}")

                # 访问每个 frame
                if src:
                    try:
                        frame_url = self.base_url + src if src.startswith('/') else src
                        resp = self.session.get(frame_url, timeout=5)
                        if '任务' in resp.text or '工时' in resp.text:
                            filename = f'frame_{i}.html'
                            with open(filename, 'w', encoding='utf-8') as f:
                                f.write(resp.text)
                            print(f"     [OK] 包含任务/工时内容，已保存到: {filename}")
                    except Exception as e:
                        print(f"     [X] 访问失败: {str(e)[:50]}")
        else:
            print("未找到 iframe/frame")

    def search_api_calls(self):
        """搜索可能的 API 调用"""
        if not self.logged_in:
            return

        print(f"\n{'='*60}")
        print("7. 搜索 API 调用...")
        print(f"{'='*60}")

        with open('main_page.html', 'r', encoding='utf-8') as f:
            content = f.read()

        # 搜索 DWR 调用
        if 'dwr' in content.lower():
            print("\n[OK] 发现 DWR 框架使用")
            # 提取 DWR 接口
            dwr_interfaces = re.findall(r'/dwr/interface/(\w+\.js)', content)
            if dwr_interfaces:
                print("  DWR 接口:")
                for interface in set(dwr_interfaces):
                    print(f"    - {interface}")

        # 搜索可能的 API URL
        print("\n搜索可能的 API URL:")
        api_patterns = [
            r'url\s*:\s*["\']([^"\']+)["\']',
            r'href\s*=\s*["\']([^"\'>\s]*\.do[^"\']*)["\']',
            r'src\s*=\s*["\']([^"\'>\s]*\.do[^"\']*)["\']',
        ]

        found_urls = set()
        for pattern in api_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if any(kw in match for kw in ['task', 'work', 'time', 'log', '任务', '工时']):
                    found_urls.add(match)

        for url in sorted(found_urls):
            print(f"  - {url}")


def main():
    print("="*60)
    print("RDM 系统探测工具")
    print("="*60)

    # 用户名保留默认值（非敏感）；密码必须运行时输入，不在源码留痕
    import getpass
    username = input("\n用户名 [tianlin]: ").strip() or "tianlin"
    password = getpass.getpass("密码（输入时不回显）: ").strip()
    if not password:
        print("[X] 密码不能为空")
        return

    explorer = RDMExplorer()

    # 登录
    if not explorer.login(username, password):
        print("\n登录失败，无法继续探测")
        return

    # 查找任务菜单
    explorer.find_task_menu()

    # 尝试常见页面
    found_pages = explorer.try_task_pages()

    # 分析 iframe
    explorer.analyze_iframes()

    # 搜索 API
    explorer.search_api_calls()

    print("\n" + "="*60)
    print("探测完成！")
    print("="*60)
    print("\n生成的文件:")
    if os.path.exists('main_page.html'):
        print("  - main_page.html (主页)")
    if found_pages:
        for url_path, filename in found_pages:
            print(f"  - {filename} ({url_path})")

    print("\n请查看这些文件，分析系统结构，或提供截图以进一步开发。")


if __name__ == "__main__":
    main()
