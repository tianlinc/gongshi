#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 RDM 登录和探测工时页面
"""

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
import re
from bs4 import BeautifulSoup


class RDMExplorer:
    """RDM 系统探测器"""

    def __init__(self, base_url="http://10.111.36.3:2029"):
        self.base_url = base_url
        self.session = requests.Session()
        self.aes_key = b"abcdefgabcdefg12"

    def encrypt(self, text):
        """AES ECB 加密"""
        cipher = AES.new(self.aes_key, AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted).decode('utf-8')

    def login(self, username, password):
        """登录系统"""
        print(f"1. 访问登录页面...")
        resp = self.session.get(f"{self.base_url}/index.jsp")

        print(f"2. 准备登录数据...")
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

        print(f"3. 提交登录...")
        resp = self.session.post(
            f"{self.base_url}/j_security_check",
            data=login_data,
            allow_redirects=True
        )

        print(f"   响应URL: {resp.url}")
        print(f"   响应长度: {len(resp.text)}")

        if "error=true" in resp.url:
            print("✗ 登录失败：用户名或密码错误")
            return False

        if "loginForm" in resp.text and "index.jsp" in resp.url:
            print("✗ 登录失败：仍在登录页面")
            return False

        print("✓ 登录成功！")
        return True

    def explore_menu(self):
        """探索系统菜单"""
        print("\n" + "="*60)
        print("探索系统菜单...")
        print("="*60)

        resp = self.session.get(f"{self.base_url}/main.do")

        # 查找工时相关链接
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 查找所有链接
        links = soup.find_all('a', href=True)
        timesheet_links = []

        for link in links:
            href = link.get('href', '')
            text = link.get_text(strip=True)

            if any(keyword in text for keyword in ['工时', '填报', '考勤', 'timesheet', 'worklog']):
                timesheet_links.append((text, href))
                print(f"✓ 找到工时链接: {text} -> {href}")

        # 查找 iframe 或 frame
        iframes = soup.find_all(['iframe', 'frame'])
        if iframes:
            print(f"\n发现 {len(iframes)} 个 frame:")
            for i, iframe in enumerate(iframes, 1):
                src = iframe.get('src', '')
                print(f"  {i}. {src}")

        # 查找 JavaScript 菜单配置
        scripts = soup.find_all('script')
        for script in scripts:
            content = script.string
            if content and '工时' in content:
                print("\n找到工时相关的 JavaScript 配置")
                # 提取可能的 URL
                urls = re.findall(r'url["\s:]+([^"\s,}]+)', content)
                for url in urls[:5]:
                    print(f"  -> {url}")

        return timesheet_links

    def try_timesheet_page(self):
        """尝试访问常见的工时页面"""
        print("\n" + "="*60)
        print("尝试常见工时页面...")
        print("="*60)

        possible_urls = [
            "/timesheet.do",
            "/worklog.do",
            "/attendance.do",
            "/worktime.do",
            "/timesheet/main.do",
            "/worklog/main.do",
            "/timesheet/input.do",
            "/worklog/input.do",
        ]

        for url in possible_urls:
            full_url = self.base_url + url
            try:
                print(f"\n尝试: {url}")
                resp = self.session.get(full_url, timeout=5)

                if resp.status_code == 200:
                    if "工时" in resp.text or "考勤" in resp.text:
                        print(f"✓ 成功！页面包含工时相关内容")
                        print(f"  响应长度: {len(resp.text)}")

                        # 保存页面用于分析
                        filename = url.replace('/', '_').strip('_') + '.html'
                        with open(filename, 'w', encoding='utf-8') as f:
                            f.write(resp.text)
                        print(f"  已保存到: {filename}")

                        return full_url, resp.text
                    else:
                        print(f"  响应正常但不包含工时关键词")
                else:
                    print(f"  ✗ 状态码: {resp.status_code}")

            except Exception as e:
                print(f"  ✗ 错误: {e}")

        return None, None

    def analyze_page(self, html):
        """分析工时页面结构"""
        print("\n" + "="*60)
        print("分析页面结构...")
        print("="*60)

        soup = BeautifulSoup(html, 'html.parser')

        # 查找表单
        forms = soup.find_all('form')
        print(f"\n找到 {len(forms)} 个表单:")
        for i, form in enumerate(forms, 1):
            action = form.get('action', '')
            method = form.get('method', 'get')
            print(f"\n表单 {i}:")
            print(f"  Action: {action}")
            print(f"  Method: {method}")

            # 查找输入字段
            inputs = form.find_all(['input', 'select', 'textarea'])
            print(f"  字段数: {len(inputs)}")
            for j, inp in enumerate(inputs[:10], 1):  # 只显示前10个
                name = inp.get('name', inp.get('id', ''))
                type_ = inp.get('type', inp.name)
                print(f"    {j}. {name} ({type_})")

        # 查找表格
        tables = soup.find_all('table')
        print(f"\n找到 {len(tables)} 个表格")

        # 查找 JavaScript
        scripts = soup.find_all('script')
        print(f"找到 {len(scripts)} 个脚本标签")

        # 查找 DWR 调用（Direct Web Remoting，一种 Java Web AJAX 框架）
        dwr_pattern = r'dwr|DWR|dwrEngine'
        if re.search(dwr_pattern, html, re.IGNORECASE):
            print("✓ 页面使用了 DWR 框架")


def main():
    print("="*60)
    print("RDM 系统 - 登录和工时页面探测")
    print("="*60)

    username = input("\n用户名 [tianlin]: ").strip() or "tianlin"
    password = input("密码 [Adapter@202606]: ").strip() or "Adapter@202606"

    explorer = RDMExplorer()

    try:
        # 1. 登录
        if not explorer.login(username, password):
            print("\n登录失败，无法继续探索")
            return

        # 2. 探索菜单
        timesheet_links = explorer.explore_menu()

        # 3. 尝试常见 URL
        found_url, html = explorer.try_timesheet_page()

        # 4. 如果找到页面，分析结构
        if html:
            explorer.analyze_page(html)

        print("\n" + "="*60)
        print("探索完成！")
        print("="*60)
        print("\n请查看保存的 HTML 文件，或使用浏览器开发者工具分析系统。")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 安装依赖: pip install requests pycryptodome beautifulsoup4
    main()
