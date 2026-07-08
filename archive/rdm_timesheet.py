#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDM 工时填报自动化程序
自动登录并填写每周工时
"""

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
from datetime import datetime, timedelta
import json


class RDMClient:
    """RDM 研发管理平台客户端"""

    def __init__(self, base_url="http://10.111.36.3:2029"):
        self.base_url = base_url
        self.session = requests.Session()
        self.aes_key = b"abcdefgabcdefg12"  # AES 加密密钥

    def encrypt(self, text):
        """AES ECB 模式加密"""
        cipher = AES.new(self.aes_key, AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted).decode('utf-8')

    def login(self, username, password):
        """登录 RDM 系统"""
        # 1. 获取登录页面和 session
        login_url = f"{self.base_url}/index.jsp"
        resp = self.session.get(login_url)

        # 2. 准备登录数据
        # 用户名：base64 + AES加密
        encrypted_username = self.encrypt(base64.b64encode(username.encode('utf-8')).decode('utf-8'))
        # 密码：base64 + AES加密
        encrypted_password = self.encrypt(base64.b64encode(password.encode('utf-8')).decode('utf-8'))

        login_data = {
            "j_username": encrypted_username,
            "j_password": encrypted_password,
            "isExpires": "1",
            "sessionIndex": "",
            "BROWSER_VERSION": "1",  # Chrome
            "REMOTE_LANGUAGE": "zh-cn"
        }

        # 3. 提交登录
        auth_url = f"{self.base_url}/j_security_check"
        resp = self.session.post(auth_url, data=login_data, allow_redirects=True)

        # 检查登录是否成功
        if "error=true" in resp.url or "无效用户名或密码" in resp.text:
            raise Exception("登录失败：用户名或密码错误")
        if "loginForm" in resp.text:
            raise Exception("登录失败：仍在登录页面")

        print(f"✓ 登录成功: {username}")
        return True

    def get_user_info(self):
        """获取用户信息"""
        # 需要根据实际系统调整 URL
        url = f"{self.base_url}/user/getUserInfo.do"
        resp = self.session.get(url)
        return resp.json() if resp.text else {}

    def get_weekly_tasks(self, year=None, month=None, week=None):
        """获取当月的任务列表"""
        # 需要根据实际系统调整 URL 和参数
        url = f"{self.base_url}/timesheet/getTasks.do"
        params = {
            "year": year or datetime.now().year,
            "month": month or datetime.now().month
        }
        resp = self.session.get(url, params=params)
        return resp.json() if resp.text else []

    def submit_timesheet(self, week_start_date, tasks):
        """
        提交工时

        Args:
            week_start_date: 周开始日期 (YYYY-MM-DD)
            tasks: 任务列表，每个任务包含：
                - task_id: 任务ID
                - task_name: 任务名称
                - daily_hours: 每天工时 [周一, 周二, 周三, 周四, 周五, 周六, 周日]
                - completion_rate: 完成率 (%)
        """
        # 需要根据实际系统调整 URL 和数据格式
        url = f"{self.base_url}/timesheet/submit.do"

        # 构建工时数据
        timesheet_data = {
            "weekStart": week_start_date,
            "tasks": tasks
        }

        resp = self.session.post(url, json=timesheet_data)
        result = resp.json() if resp.text else {}

        if result.get("success"):
            print(f"✓ 工时提交成功")
        else:
            print(f"✗ 工时提交失败: {result.get('message', '未知错误')}")

        return result


def interactive_fill_timesheet():
    """交互式工时填报"""
    print("=" * 60)
    print("RDM 工时填报系统 - 自动化工具")
    print("=" * 60)

    # 用户输入
    username = input("用户名 [tianlin]: ").strip() or "tianlin"
    password = input("密码 [Adapter@202606]: ").strip() or "Adapter@202606"

    # 创建客户端
    client = RDMClient()

    try:
        # 登录
        client.login(username, password)

        print("\n请选择操作：")
        print("1. 查看/填写本周工时")
        print("2. 查看/填写指定周工时")
        print("3. 查看/填写本月所有工时")
        print("4. 退出")

        choice = input("\n请选择 [1-4]: ").strip()

        if choice == "1":
            # 本周
            week_start = get_week_start()
            print(f"\n本周开始日期: {week_start}")
            fill_week_timesheet(client, week_start)

        elif choice == "2":
            # 指定周
            week_start = input("请输入周开始日期 (YYYY-MM-DD): ").strip()
            fill_week_timesheet(client, week_start)

        elif choice == "3":
            # 本月所有周
            year = datetime.now().year
            month = datetime.now().month
            fill_month_timesheet(client, year, month)

        else:
            print("退出系统")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


def get_week_start(date=None):
    """获取本周一日期"""
    if date is None:
        date = datetime.now()
    # 周一为一周的开始
    week_start = date - timedelta(days=date.weekday())
    return week_start.strftime("%Y-%m-%d")


def fill_week_timesheet(client, week_start):
    """填写一周工时"""
    print(f"\n正在处理周: {week_start}")

    # TODO: 从系统获取任务列表
    print("\n正在获取任务列表...")
    # tasks = client.get_weekly_tasks()

    # 简化版：手动输入任务
    tasks = []
    while True:
        print(f"\n--- 任务 {len(tasks) + 1} ---")
        task_name = input("任务名称（留空结束）: ").strip()
        if not task_name:
            break

        print("请输入每天工时（周一到周日，空格分隔，如: 8 8 8 8 8 0 0）:")
        hours_input = input().strip()
        daily_hours = [float(h) for h in hours_input.split()]

        completion_rate = float(input("完成率 (%) [100]: ").strip() or "100")

        tasks.append({
            "task_name": task_name,
            "daily_hours": daily_hours,
            "completion_rate": completion_rate
        })

    if tasks:
        print("\n工时汇总:")
        print("-" * 60)
        for i, task in enumerate(tasks, 1):
            total_hours = sum(task["daily_hours"])
            print(f"{i}. {task['task_name']}")
            print(f"   工时: {' + '.join(map(str, task['daily_hours']))} = {total_hours} 小时")
            print(f"   完成率: {task['completion_rate']}%")

        confirm = input("\n确认提交？[Y/n]: ").strip().lower()
        if confirm in ['y', 'yes', '']:
            # client.submit_timesheet(week_start, tasks)
            print("✓ 工时已提交（演示模式，未实际提交）")
        else:
            print("已取消提交")
    else:
        print("未录入任何任务")


def fill_month_timesheet(client, year, month):
    """填写整月工时"""
    print(f"\n正在处理: {year}年{month}月")

    # TODO: 实现整月工时填写逻辑
    print("功能开发中...")


if __name__ == "__main__":
    # 先安装依赖: pip install pycryptodome requests
    interactive_fill_timesheet()
