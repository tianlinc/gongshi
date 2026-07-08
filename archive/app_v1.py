#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDM 工时填报 Web 应用
带图形界面的工时管理系统
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
import requests
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)


class RDMClient:
    """RDM 客户端"""

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
        """登录 RDM 系统"""
        try:
            # 获取登录页面
            self.session.get(f"{self.base_url}/index.jsp")

            # 加密用户名和密码
            encrypted_username = self.encrypt(
                base64.b64encode(username.encode('utf-8')).decode('utf-8')
            )
            encrypted_password = self.encrypt(
                base64.b64encode(password.encode('utf-8')).decode('utf-8')
            )

            # 提交登录
            login_data = {
                "j_username": encrypted_username,
                "j_password": encrypted_password,
                "isExpires": "1",
                "sessionIndex": "",
                "BROWSER_VERSION": "1",
                "REMOTE_LANGUAGE": "zh-cn"
            }

            resp = self.session.post(
                f"{self.base_url}/j_security_check",
                data=login_data,
                allow_redirects=True
            )

            # 检查登录结果
            if "error=true" in resp.url or "无效用户名或密码" in resp.text:
                return {"success": False, "message": "用户名或密码错误"}

            if "loginForm" in resp.text and len(resp.text) < 10000:
                return {"success": False, "message": "登录失败，请重试"}

            self.username = username
            return {"success": True, "message": "登录成功"}

        except Exception as e:
            return {"success": False, "message": f"登录出错: {str(e)}"}

    def get_tasks(self, year=None, month=None):
        """获取任务列表（示例）"""
        # TODO: 根据实际系统实现
        # 这里返回模拟数据
        return {
            "success": True,
            "tasks": [
                {"id": "1", "name": "项目开发"},
                {"id": "2", "name": "需求分析"},
                {"id": "3", "name": "代码评审"},
            ]
        }

    def submit_timesheet(self, week_data):
        """提交工时"""
        # TODO: 根据实际系统实现
        print("提交工时:", json.dumps(week_data, indent=2, ensure_ascii=False))

        # 模拟提交
        return {
            "success": True,
            "message": "工时提交成功（演示模式）"
        }


# 全局客户端
rdm_client = None


@app.route('/')
def index():
    """首页"""
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login():
    """登录接口"""
    global rdm_client

    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({"success": False, "message": "用户名和密码不能为空"})

    # 创建客户端并登录
    rdm_client = RDMClient()
    result = rdm_client.login(username, password)

    if result['success']:
        session['logged_in'] = True
        session['username'] = username

    return jsonify(result)


@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    """仪表板"""
    if 'logged_in' not in session:
        return redirect(url_for('index'))
    return render_template('dashboard.html', username=session.get('username'))


@app.route('/api/week-info')
def get_week_info():
    """获取周信息"""
    today = datetime.now()

    # 获取本周一
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    days = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        days.append({
            "date": day.strftime("%Y-%m-%d"),
            "day": day.day,
            "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][i],
            "is_weekend": i >= 5,
            "is_today": day.date() == today.date()
        })

    return jsonify({
        "success": True,
        "week_start": week_start.strftime("%Y-%m-%d"),
        "week_end": week_end.strftime("%Y-%m-%d"),
        "week_number": week_start.isocalendar()[1],
        "days": days
    })


@app.route('/api/tasks')
def get_tasks():
    """获取任务列表"""
    if not rdm_client:
        return jsonify({"success": False, "message": "未登录"})

    year = request.args.get('year', datetime.now().year)
    month = request.args.get('month', datetime.now().month)

    result = rdm_client.get_tasks(year, month)
    return jsonify(result)


@app.route('/api/submit-timesheet', methods=['POST'])
def submit_timesheet():
    """提交工时"""
    if not rdm_client:
        return jsonify({"success": False, "message": "未登录"})

    data = request.json
    result = rdm_client.submit_timesheet(data)
    return jsonify(result)


@app.route('/api/preview', methods=['POST'])
def preview():
    """预览工时"""
    data = request.json

    # 计算总工时
    total_hours = 0
    task_summary = []

    for task in data.get('tasks', []):
        task_total = sum(task.get('hours', []))
        total_hours += task_total
        task_summary.append({
            "name": task.get('name'),
            "total_hours": task_total,
            "completion_rate": task.get('completionRate', 100)
        })

    return jsonify({
        "success": True,
        "total_hours": total_hours,
        "task_summary": task_summary
    })


if __name__ == '__main__':
    print("=" * 60)
    print("RDM 工时填报系统 - Web 版")
    print("=" * 60)
    print("\n启动服务器...")
    print("请在浏览器中访问: http://localhost:5000")
    print("\n按 Ctrl+C 停止服务器\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
