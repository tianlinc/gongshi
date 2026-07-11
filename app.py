#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDM 工时填报系统 v2 - 单文件后端

实现内容：
- RDMClient：登录（双重编码 AES-ECB）、统一 _request、
  get_my_tasks（任务列表抓取）、
  get_week_existing（解析 unBody）、submit_day（entity.jsf → taskForm:save 简单提交）
- 模块级 clients dict（保留 v1 session 模型，flask.session 仅存 username + logged_in）
- 6 个路由：GET / + GET /dashboard + POST /api/login + POST /api/logout +
  GET /api/tasks + GET /api/timesheet + POST /api/submit-day
- @before_request 拦截 /api/* 未登录请求，统一返回 {success:false, message:'未登录'} 状态码 200

约定：UI 字符串中文；print 用 [OK]/[X]；GBK 编码统一处理。
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, after_this_request
from flask_cors import CORS
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse
import html
import json
import os
import re
import time
import threading
import logging
from bs4 import BeautifulSoup
from license_utils import (
    generate_sn, generate_license, verify_license,
    read_status, write_status, check_activated, activate,
)
import rdm_config

app = Flask(__name__)
app.secret_key = b'rdm_timesheet_secret_key_2026'
CORS(app)

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('gongshi')
log.setLevel(logging.INFO)  # 默认 INFO；app.debug 时在 main 中切换 DEBUG


def _read_app_version():
    """读取项目根目录 VERSION 文件，返回版本号字符串。失败回退 '0.0.0'。"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_dir, 'VERSION'), 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return '0.0.0'


# ===========================================================================
# _unplannedInfo 编码常量（来自 scripts/myspace/unplannedTask.js 实证）
# DEPRECATED（2026-06-23）：submit_day() 已改用 entity.jsf → taskForm:save 路径，
# _unplannedInfo 编码不再使用。以下代码保留供参考，待路径 C 完全验证后可安全删除。
# ===========================================================================

S1 = "#-@%!-@#"        # 字段间分隔符
S2 = "#-%@-#@"         # 字段名 vs 值
S3 = "#-%#!#-@-#@"     # 任务行之间
S4 = "#-%#!A-#-@-#@"   # 字段名 vs day 值

# 状态白名单：RN=进行中, NR=未启动（HAR 实证：RDM HTML 中 status 属性值为 NR 非 NS）
FILLABLE_STATUSES = {'RN', 'NR'}
STATUS_TEXT_MAP = {'RN': '进行中', 'NR': '未启动'}

# 任务列表抓取模式：True=纯 HTTP(A4J AJAX) 抓取
# INSPUR-73: HTTP 模式已验证通过，默认启用
USE_HTTP_TASKS = True


def encode_unplanned_info_single_day(task_id: str, day_index: int,
                                     hour: float, completion_rate):
    """
    构造 _unplannedInfo 字符串（仅一个任务、仅一个 day）。

    DEPRECATED（2026-06-23）：entity.jsf 路径不需要此编码，保留供参考。

    序列化模板（架构 §2.5）：
        {task_id}{S1}{day_csv_no_trailing_comma}
        {S1}{day}{S2}_rate{S4}{rate}{S2}_effort{S4}{hour}{S2}_remark{S4} {S2}_issue{S4}
        {S3}

    注意：JS 端 day-csv 是去掉末尾逗号后的字符串（"3," → "3"）。
    rate / effort / remark / issue 缺值时填单空格 " "（与 composeUnInfo 的 g||" " 一致）。
    """
    rate_str = "" if completion_rate is None else str(int(completion_rate))
    if rate_str == "":
        rate_str = " "
    effort_str = _format_hour(hour)

    parts = []
    parts.append(task_id if task_id else " ")
    parts.append(S1)
    parts.append(str(day_index))                 # day-csv（仅一天）
    parts.append(S1)
    parts.append(str(day_index))                 # 重复 day 头
    parts.append(S2 + "_rate" + S4 + rate_str)
    parts.append(S2 + "_effort" + S4 + effort_str)
    parts.append(S2 + "_remark" + S4 + " ")
    parts.append(S2 + "_issue" + S4 + " ")
    parts.append(S3)
    return "".join(parts)


def _format_hour(h):
    """工时数字格式化：整数去小数点（INSPUR-23：工时仅接受整数）"""
    if h is None:
        return " "
    return str(int(float(h)))


def normalize_to_monday(date_str: str) -> str:
    """容错：传入 YYYY-MM-DD，返回该周周一 YYYY-MM-DD"""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    monday = d - timedelta(days=d.weekday())
    return monday.strftime("%Y-%m-%d")


# ===========================================================================
# RDMClient
# ===========================================================================

class RDMClient:
    """RDM 系统客户端"""

    def __init__(self, base_url=None):
        if base_url is None:
            base_url = rdm_config.get_rdm_base_url()
        self.base_url = base_url
        self.session = requests.Session()
        # P3 修复：跳过系统代理（RDM 是内网服务器，应直连）
        # 系统代理（如 Clash @ 127.0.0.1:7892）可能无法转发内网 IP 导致超时
        self.session.trust_env = False
        # §2.2：必须带浏览器 UA，否则服务器随机断连
        self.session.headers.update({
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        self.aes_key = b"abcdefgabcdefg12"
        self.username = ""
        self._password = ""  # P2 加固：存储密码用于 ViewState 过期自动重登
        self._login_user_id = None  # 惰性加载，用于 dailyReport.jsf 行记录过滤

    # ----- 加密（v1 验证有效，原样保留） -----
    def encrypt(self, text):
        """AES ECB 加密（base64 → AES-ECB → base64）"""
        cipher = AES.new(self.aes_key, AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted).decode('utf-8')

    # ----- 统一 HTTP 请求（含 connection-level 重试 + 编码归一） -----
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        所有对 RDM 的请求都过这里：
        - connection-level 重试：ConnectionError/Timeout 最多重试 2 次
        - 统一 r.encoding = r.apparent_encoding or 'gbk'
        - HTTP 4xx/5xx 不重试
        """
        url = path if path.startswith('http') else f"{self.base_url}{path}"
        kwargs.setdefault('timeout', 15)

        last_exc = None
        for attempt in range(3):
            try:
                r = self.session.request(method, url, **kwargs)
                # 统一编码
                try:
                    r.encoding = r.apparent_encoding or 'gbk'
                except Exception:
                    r.encoding = 'gbk'
                return r
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:
                last_exc = e
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise
        # unreachable
        raise last_exc  # type: ignore

    # ----- 登录 -----
    def login(self, username, password):
        """登录系统"""
        try:
            # 拿 cookie / JSESSIONID
            self._request('GET', '/index.jsp')

            # 双重编码：base64 → AES-ECB → base64
            encrypted_username = self.encrypt(
                base64.b64encode(username.encode('utf-8')).decode('utf-8')
            )
            encrypted_password = self.encrypt(
                base64.b64encode(password.encode('utf-8')).decode('utf-8')
            )

            login_data = {
                "j_username": encrypted_username,
                "j_password": encrypted_password,
                "isExpires": "1",
                "sessionIndex": "",
                "BROWSER_VERSION": "1",
                "REMOTE_LANGUAGE": "zh-cn",
            }

            resp = self._request(
                'POST', '/j_security_check',
                data=login_data, allow_redirects=True,
            )

            if "error=true" in resp.url or "无效用户名或密码" in resp.text:
                return {"success": False, "message": "用户名或密码错误"}

            if "loginForm" in resp.text and len(resp.text) < 15000:
                return {"success": False, "message": "登录失败，请重试"}

            self.username = username
            self._password = password  # P2 加固：存储密码用于 ViewState 过期自动重登
            return {"success": True, "message": "登录成功"}

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout):
            return {"success": False, "message": "网络异常，请稍后重试"}
        except Exception as e:
            log.exception("[X] login error")
            return {"success": False, "message": f"登录出错: {str(e)}"}

    # ----- 我的任务列表（HTTP A4J 引擎，INSPUR-73）-----
    def get_my_tasks_http(self):
        """
        HTTP 直连版：用 requests 发 A4J AJAX 请求取代 Playwright 浏览器抓取。

        流程：GET myTask.jsf → POST cate=0（我负责）→ POST cate=22（我参与）
        每个 POST 的 XML 响应中直接用 BeautifulSoup 解析 tr.body-row。
        """
        merged = {}

        # 1. GET myTask.jsf：获取初始 ViewState + AJAXREQUEST container ID
        r = self._request('GET', '/pages/task/list/myTask.jsf')
        soup = BeautifulSoup(r.text, 'html.parser')

        view_state = self._parse_view_state(soup)
        if not view_state:
            print("[X] myTask.jsf 未拿到 ViewState")
            return []

        # 提取 AJAXREQUEST（JSF container ID）
        ajaxrequest = ''
        m = re.search(r"A4J\.AJAX\.Submit\('([^']+)'", r.text)
        if m:
            ajaxrequest = m.group(1)
        else:
            m = re.search(r"j_id_jsp_\d+_\d+", r.text)
            if m:
                ajaxrequest = m.group(0)

        if not ajaxrequest:
            print("[X] myTask.jsf 未拿到 AJAXREQUEST")
            return []

        # 2. 循环两个 scope
        for cate, label in [("0", "我负责"), ("22", "我参与")]:
            r, view_state = self._a4j_fetch_tasks(
                ajaxrequest, view_state, cate, label
            )
            tasks = self._parse_a4j_tasks(r.text, label)
            for t in tasks:
                tid = t['task_id']
                if tid in merged:
                    merged[tid]['source'] = 'both'
                else:
                    merged[tid] = t

        # 3. 过滤 status ∈ {RN, NR}
        result = []
        for t in merged.values():
            st = t.get('status_code', '')
            if st in FILLABLE_STATUSES:
                t['status'] = STATUS_TEXT_MAP.get(st, st)
                result.append({
                    'task_id': t['task_id'],
                    'name': t['name'],
                    'project': t['project'],
                    'project_id': t.get('project_id', ''),
                    'status': t['status'],
                    'status_code': t['status_code'],
                    'source': t['source'],
                    'plan_start': t.get('plan_start', ''),
                    'plan_end': t.get('plan_end', ''),
                })
            elif st and st not in ('FN', 'TC', 'SP', 'FS', ''):
                print(f"[OK] 未知任务状态 status={st} name={t.get('name','')}")

        print(f"[OK] 获取任务 {len(result)} 条 user={self.username}")
        return result

    def _a4j_fetch_tasks(self, ajaxrequest, view_state, cate, label):
        """
        发一次 A4J AJAX POST 到 myTask.jsf 获取指定 scope 的任务列表。

        返回 (response, new_view_state)。
        """
        form_data = {
            'AJAXREQUEST': ajaxrequest,
            'operate': 'operate',
            'page': '',
            'cate': cate,
            'type': 'TSK',
            'module': 'TSK',
            'planId': '',
            'refreshType': '0',
            'isInit': 'N',
            'nodeId': 'value%3D%22',
            'projectIds': '',
            'taskName': '',
            'emptySearch': '',
            'baseSearch': '',
            'hasPlanOwner': '',
            'showFCTask': 'N',
            'condition': '',
            'isOwner': '',
            'light': '',
            'pjtTask': '',
            'userId': '',
            'objectId': '',
            'filterIds': '',
            'operate:_path': '',
            'operate:_fileName': '',
            'operate:_fileContentType': '',
            'javax.faces.ViewState': view_state,
            'operate:refreshBody': 'operate:refreshBody',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Faces-Request': 'partial/ajax',
        }

        if app.debug:
            log.debug("[DEBUG] _a4j_fetch_tasks POST %s cate=%s", label, cate)

        r = self._request(
            'POST',
            '/pages/task/list/myTask.jsf',
            data=form_data,
            headers=headers,
        )
        print(f"[OK] {label} HTTP 请求完成 status={r.status_code} len={len(r.text)}")

        # 从 XML 响应中提取新的 ViewState
        new_vs = view_state  # fallback
        try:
            xml_soup = BeautifulSoup(r.text, 'html.parser')
            vs_input = xml_soup.find(
                'input', attrs={'name': 'javax.faces.ViewState'}
            )
            if vs_input and vs_input.get('value'):
                new_vs = vs_input['value']
        except Exception:
            pass

        return r, new_vs

    @staticmethod
    def _parse_a4j_tasks(xml_text, label):
        """
        从 myTask.jsf A4J XML 响应中解析任务列表。

        XML 结构：<div id="taskPanel"> → <table> → <tbody> → <tr class="body-row">
        task_id 来自 tr#id, status 来自 tr#status。
        字段映射：td[5]=任务名, td[7]=项目名+project_id, td[9]=plan_start, td[10]=plan_end
        """
        soup = BeautifulSoup(xml_text, 'html.parser')
        rows = soup.find_all('tr', class_='body-row')

        tasks = []
        for row in rows:
            tid = row.get('id', '')
            status = row.get('status', '')
            tds = row.find_all('td')

            name = ''
            project = ''
            project_id = ''
            plan_start = ''
            plan_end = ''

            if len(tds) > 5:
                a = tds[5].find('a')
                name = (a.get_text(strip=True) if a
                        else tds[5].get_text(strip=True))

            if len(tds) > 7:
                a = tds[7].find('a')
                if a:
                    project = a.get_text(strip=True)
                    onclick = a.get('onclick', '')
                    m = re.search(r"openEntity\(['\"]([^'\"]+)['\"]", onclick)
                    if m:
                        project_id = m.group(1)

            if len(tds) > 10:
                plan_start = tds[9].get_text(strip=True)
                plan_end = tds[10].get_text(strip=True)

            tasks.append({
                'task_id': tid,
                'name': name,
                'project': project,
                'project_id': project_id,
                'status_code': status,
                'plan_start': plan_start,
                'plan_end': plan_end,
                'source': label,
            })

        print(f"[OK] {label} 解析 {len(tasks)} 条任务")
        return tasks


    # ----- 任务缓存（JSON 文件缓存，TTL 4h）-----
    def _get_cache_path(self, username):
        """返回缓存文件路径 cache/{username}_tasks.json"""
        return os.path.join('cache', f'{username}_tasks.json')

    def _load_cache(self):
        """读取缓存文件，过期/损坏/不存在返回 None"""
        path = self._get_cache_path(self.username)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception):
            return None

        expires_at = data.get('expires_at', '')
        if expires_at:
            try:
                expire_time = datetime.fromisoformat(expires_at)
                if datetime.now() >= expire_time:
                    return None
            except Exception:
                return None

        tasks = data.get('tasks')
        if not isinstance(tasks, list):
            return None

        return {
            'tasks': tasks,
            'cached_at': data.get('cached_at', ''),
            'expires_at': expires_at,
        }

    def _write_cache(self, tasks):
        """写入缓存文件，确保 cache/ 目录存在"""
        cache_dir = 'cache'
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        now = datetime.now()
        expires = now + timedelta(hours=4)
        cache_data = {
            'cached_at': now.isoformat(),
            'expires_at': expires.isoformat(),
            'total_count': len(tasks),
            'tasks': tasks,
        }

        path = self._get_cache_path(self.username)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_view_state(soup) -> str:
        """从已解析的 BeautifulSoup 里抓 javax.faces.ViewState"""
        el = soup.find('input', attrs={'name': 'javax.faces.ViewState'})
        if el and el.get('value'):
            return el['value']
        return ''

    def _get_login_user_id(self) -> str:
        """
        惰性获取当前登录用户的 RDM 内部 ID（UUID）。

        从 workLogView.jsf 的 loginUser hidden input 提取，仅请求一次并缓存。
        用于 dailyReport.jsf 行记录的按用户过滤。
        """
        if self._login_user_id:
            return self._login_user_id

        try:
            r = self._request(
                'GET',
                '/pages/myspace/log/workLogView.jsf'
                '?isView=N&userId=&reportId=&startDate=2026-01-05',
            )
            soup = BeautifulSoup(r.text, 'html.parser')
            lu = soup.find('input', id='loginUser')
            if lu and lu.get('value'):
                self._login_user_id = lu['value']
        except Exception as e:
            log.warning("[X] _get_login_user_id 获取失败: %s", e)

        return self._login_user_id or ''

    # ----- 实体页上下文（entity.jsf → taskForm:save 提交路径）-----
    def get_entity_page(self, task_id: str) -> dict:
        """
        GET entity.jsf 获取 ViewState 和 AJAX container ID。

        用于 submit_day() 的新提交路径（替代 workLogView.jsf → saveLog）。
        container_id 提取策略（按优先级）：
        1. 搜索 taskForm:save 按钮 onclick 中的 A4J.AJAX.Submit 调用
        2. 搜索页面中任意 A4J.AJAX.Submit 调用（fallback）
        3. 搜索 id="j_id_jsp_*" 模式的 JSF 生成 ID（最终 fallback）

        返回 {'view_state': str, 'container_id': str}
        """
        path = f"/pages/task/entity.jsf?taskId={task_id}&action=1&planRight=&date="
        r = self._request('GET', path)
        soup = BeautifulSoup(r.text, 'html.parser')

        vs = soup.find('input', {'name': 'javax.faces.ViewState'})
        view_state = vs['value'] if vs else ''

        # 提取 AJAX container ID
        container_id = ''
        # 策略 1: taskForm:save 按钮的 onclick
        m = re.search(r"taskForm:save.*?A4J\.AJAX\.Submit\('([^']+)'",
                      r.text, re.DOTALL)
        if m:
            container_id = m.group(1)
        # 策略 2: 任意 A4J.AJAX.Submit
        if not container_id:
            m = re.search(r"A4J\.AJAX\.Submit\('([^']+)'", r.text)
            if m:
                container_id = m.group(1)
        # 策略 3: JSF 生成的 form/container ID
        if not container_id:
            m = re.search(r"id=\"(j_id_jsp_[^\"]+)\"", r.text)
            if m:
                container_id = m.group(1)

        return {
            'view_state': view_state,
            'container_id': container_id,
        }

    # ----- 执行日报（dailyReport.jsf → 按任务维度回填已填工时）-----
    def get_daily_report(self, task_id: str) -> dict:
        """
        GET /pages/task/dailyReport.jsf?taskId=<task_id>，解析执行日报表格。

        该页面按任务维度展示所有填报记录（含多用户），相比 workLogView.jsf
        的按周视图数据更全面。

        返回 {date_str: {hour: float, rate: int}, ...}，只含当前登录用户的记录。
        A4J 分页自动处理。
        """
        result = {}

        # ----- 第 1 页：GET -----
        path = f"/pages/task/dailyReport.jsf?taskId={task_id}"
        r = self._request('GET', path)
        soup = BeautifulSoup(r.text, 'html.parser')

        view_state = self._parse_view_state(soup)
        if not view_state:
            raise RuntimeError("dailyReport.jsf 未拿到 ViewState")

        # 提取 A4J AJAX container ID（页内搜索按钮 onclick）
        container_id = ''
        m = re.search(r"A4J\.AJAX\.Submit\('(j_id_jsp_\d+_\d+)','operate'",
                      r.text)
        if m:
            container_id = m.group(1)

        # 解析第 1 页行记录
        self._parse_daily_report_rows(soup, result)

        # ----- 检查分页 -----
        page_table = soup.find('table', class_='page-table')
        max_page = 1
        if page_table:
            for a in page_table.find_all('a'):
                onclick = a.get('onclick', '')
                m2 = re.search(r"getByTargetPage\('(\d+)'\)", onclick)
                if m2:
                    p = int(m2.group(1))
                    if p > max_page:
                        max_page = p

        # ----- 逐页 POST 获取剩余数据 -----
        for page in range(2, max_page + 1):
            try:
                page_soup = self._fetch_daily_report_page(
                    task_id, view_state, container_id, page
                )
                if page_soup:
                    self._parse_daily_report_rows(page_soup, result)
                else:
                    log.warning(
                        "[X] dailyReport 第 %d 页返回空，停止分页", page
                    )
                    break
            except Exception as e:
                log.warning(
                    "[X] dailyReport 第 %d 页请求失败: %s", page, e
                )
                break

        return result

    def _fetch_daily_report_page(self, task_id: str, view_state: str,
                                  container_id: str, page: int):
        """
        POST dailyReport.jsf 分页请求（A4J AJAX）。

        返回 BeautifulSoup 对象（从 XML partial response 中提取 <update> 内容），
        失败返回 None。
        """
        form = {
            'AJAXREQUEST': container_id,
            'operate': 'operate',
            'operate:search': 'operate:search',
            'targetPage': str(page),
            '_targetPage': str(page),
            'taskId': task_id,
            'javax.faces.ViewState': view_state,
        }
        headers = {
            'Faces-Request': 'partial/ajax',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type':
                'application/x-www-form-urlencoded; charset=UTF-8',
        }

        r = self._request(
            'POST', '/pages/task/dailyReport.jsf',
            data=form, headers=headers,
        )

        if r.status_code != 200:
            log.warning("[X] dailyReport 分页 POST 返回 %d", r.status_code)
            return None

        text = r.text or ''

        # A4J partial response 格式：
        # <partial-response><changes><update id="..."><![CDATA[...]]></update>
        # 提取 CDATA 中的 HTML 片段并用 BeautifulSoup 解析
        cdata_matches = re.findall(
            r'<\!\[CDATA\[(.*?)\]\]>', text, re.DOTALL
        )
        if cdata_matches:
            # 合并所有 CDATA 片段
            combined = '\n'.join(cdata_matches)
            return BeautifulSoup(combined, 'html.parser')

        # 如果没有 CDATA，可能整个响应的 body 就是 HTML（某些版本）
        if '<tr class="body-row"' in text:
            return BeautifulSoup(text, 'html.parser')

        return None

    def _parse_daily_report_rows(self, soup, result: dict) -> None:
        """
        从已解析的 BeautifulSoup 对象中提取 dailyReport 行记录，
        按当前用户过滤后写入 result（in-place 更新）。

        表格列映射（8 列）：
          0=序号  1=执行人  2=执行日期  3=填写日期
          4=完成率  5=填报工作量  6=存在问题  7=描述

        用户过滤策略：
          1. 优先：匹配 <a> 文本（执行人姓名）== self.username
          2. 备选：匹配 showUserDetail('ID') == self._get_login_user_id()
          3. 兜底：两个条件都匹配不上时返回空（不纳入其他用户的记录）
        """
        login_user_id = self._get_login_user_id()

        rows = soup.find_all('tr', class_='body-row')
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 6:
                continue

            # --- 执行人列（col 1）：姓名 + user ID ---
            executor_name = ''
            executor_user_id = ''
            a_tag = tds[1].find('a')
            if a_tag:
                executor_name = a_tag.get_text(strip=True)
                onclick = a_tag.get('onclick', '')
                m = re.search(r"showUserDetail\('([^']+)'\)", onclick)
                if m:
                    executor_user_id = m.group(1)

            # --- 用户过滤 ---
            # 策略 1: 姓名匹配
            name_match = (executor_name and executor_name == self.username)
            # 策略 2: user ID 匹配
            id_match = (
                login_user_id
                and executor_user_id
                and executor_user_id == login_user_id
            )

            if not name_match and not id_match:
                # 不纳入其他用户的记录
                # 若两个条件都无数据（self.username 为空且 login_user_id
                # 为空），不返回任何记录 —— 避免泄露其他人数据
                continue

            # --- 执行日期（col 2）---
            date_div = tds[2].find('div')
            date_str = date_div.get_text(strip=True) if date_div else tds[2].get_text(strip=True)
            if not date_str:
                continue

            # --- 完成率（col 4）---
            rate_div = tds[4].find('div')
            rate_text = rate_div.get_text(strip=True) if rate_div else tds[4].get_text(strip=True)
            rate_text = rate_text.replace('%', '').strip()
            rate_val = 0
            try:
                rate_val = int(float(rate_text))
            except (ValueError, TypeError):
                pass

            # --- 填报工作量（col 5）---
            hour_div = tds[5].find('div')
            hour_text = hour_div.get_text(strip=True) if hour_div else tds[5].get_text(strip=True)
            hour_val = 0.0
            try:
                hour_val = float(hour_text)
            except (ValueError, TypeError):
                pass

            # --- 合并结果 ---
            if date_str in result:
                result[date_str]['hour'] += hour_val
                result[date_str]['rate'] = max(result[date_str]['rate'],
                                                rate_val)
            else:
                result[date_str] = {'hour': hour_val, 'rate': rate_val}

    # ----- 全员日报（dailyReport.jsf → 所有成员日报）-----
    def get_team_logs(self, task_id: str) -> list:
        """
        GET /pages/task/dailyReport.jsf?taskId=<task_id>，解析所有成员执行日报。

        与 get_daily_report() 的区别：
        - 不过滤当前用户，返回该任务下所有成员的日报记录
        - 每条记录包含：成员名、日期、工时、完成率、存在问题、描述
        - A4J 分页自动处理

        返回 [{member_name, date, hour, rate, issue, description}, ...]
        """
        result = []

        # ---- 第 1 页：GET ----
        path = f"/pages/task/dailyReport.jsf?taskId={task_id}"
        r = self._request('GET', path)
        soup = BeautifulSoup(r.text, 'html.parser')

        view_state = self._parse_view_state(soup)
        if not view_state:
            raise RuntimeError("dailyReport.jsf 未拿到 ViewState")

        # 提取 A4J AJAX container ID
        container_id = ''
        m = re.search(r"A4J\.AJAX\.Submit\('(j_id_jsp_\d+_\d+)','operate'",
                      r.text)
        if m:
            container_id = m.group(1)

        # 解析第 1 页行记录（全员）
        self._parse_team_log_rows(soup, result)

        # ---- 检查分页 ----
        page_table = soup.find('table', class_='page-table')
        max_page = 1
        if page_table:
            for a in page_table.find_all('a'):
                onclick = a.get('onclick', '')
                m2 = re.search(r"getByTargetPage\('(\d+)'\)", onclick)
                if m2:
                    p = int(m2.group(1))
                    if p > max_page:
                        max_page = p

        # ---- 逐页 POST 获取剩余数据 ----
        for page in range(2, max_page + 1):
            try:
                page_soup = self._fetch_daily_report_page(
                    task_id, view_state, container_id, page
                )
                if page_soup:
                    self._parse_team_log_rows(page_soup, result)
                else:
                    log.warning(
                        "[X] team_logs 第 %d 页返回空，停止分页", page
                    )
                    break
            except Exception as e:
                log.warning(
                    "[X] team_logs 第 %d 页请求失败: %s", page, e
                )
                break

        return result

    def _parse_team_log_rows(self, soup, result: list) -> None:
        """
        从 dailyReport.jsf 页面解析所有成员日报行（不过滤用户，与
        _parse_daily_report_rows 的区别是不过滤当前用户且提取更多字段）。

        表格列映射（8 列）：
          0=序号  1=执行人  2=执行日期  3=填写日期
          4=完成率  5=填报工作量  6=存在问题  7=描述
        """
        rows = soup.find_all('tr', class_='body-row')
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 6:
                continue

            # --- 执行人（col 1）---
            member_name = ''
            a_tag = tds[1].find('a')
            if a_tag:
                member_name = a_tag.get_text(strip=True)

            # --- 执行日期（col 2）---
            date_div = tds[2].find('div')
            date_str = (date_div.get_text(strip=True)
                        if date_div else tds[2].get_text(strip=True))
            if not date_str:
                continue

            # --- 完成率（col 4）---
            rate_div = tds[4].find('div')
            rate_text = (rate_div.get_text(strip=True)
                         if rate_div else tds[4].get_text(strip=True))
            rate_text = rate_text.replace('%', '').strip()
            rate_val = 0
            try:
                rate_val = int(float(rate_text))
            except (ValueError, TypeError):
                pass

            # --- 填报工作量（col 5）---
            hour_div = tds[5].find('div')
            hour_text = (hour_div.get_text(strip=True)
                         if hour_div else tds[5].get_text(strip=True))
            hour_val = 0.0
            try:
                hour_val = float(hour_text)
            except (ValueError, TypeError):
                pass

            # --- 存在问题（col 6）---
            issue = ''
            if len(tds) > 6:
                issue_div = tds[6].find('div')
                issue = (issue_div.get_text(strip=True)
                         if issue_div else tds[6].get_text(strip=True))

            # --- 描述（col 7）---
            description = ''
            if len(tds) > 7:
                desc_div = tds[7].find('div')
                description = (desc_div.get_text(strip=True)
                               if desc_div else tds[7].get_text(strip=True))

            result.append({
                'member_name': member_name,
                'date': date_str,
                'hour': hour_val,
                'rate': rate_val,
                'issue': issue,
                'description': description,
            })

    # ----- 工时回填 -----
    def get_week_existing(self, week_start: str):
        """
        GET /pages/myspace/log/workLogView.jsf?startDate=<周一>，解析整周已填工时。

        返回：
            {
              'view_state': str,
              'report_id':  str,
              'login_user_id': str,
              'data_json':  str,        # 原始字符串，回传 saveLog 时透传
              'entries':    [{task_id, hours[7], completion_rates[7]}, ...]
            }
        """
        week_start = normalize_to_monday(week_start)
        path = (f"/pages/myspace/log/workLogView.jsf"
                f"?isView=N&userId=&reportId=&startDate={week_start}")

        r = self._request('GET', path)
        if r.status_code != 200:
            raise RuntimeError(f"工时页加载失败 (HTTP {r.status_code})")

        soup = BeautifulSoup(r.text, 'html.parser')

        view_state = self._parse_view_state(soup)
        if not view_state:
            raise RuntimeError("工时页未拿到 ViewState")

        # data 字段：HTML 实体编码后存在 <input id="data" value="...">
        data_input = soup.find('input', id='data')
        data_raw = ''
        data_obj = {}
        if data_input and data_input.get('value'):
            data_raw = data_input['value']
            try:
                # value 在 HTML 里已被实体编码，BeautifulSoup 取出来是已解码的字符串
                data_obj = json.loads(data_raw)
            except Exception as e:
                log.warning("[X] 解析 data 字段失败：%s", e)
                data_obj = {}

        # loginUser
        login_user = ''
        lu = soup.find('input', id='loginUser')
        if lu and lu.get('value'):
            login_user = lu['value']

        # reportId
        report_id = ''
        rid = soup.find('input', id='reportId')
        if rid and rid.get('value'):
            report_id = rid['value']

        # 解析 unBody
        entries = self._parse_un_body(data_obj.get('unBody', []))

        return {
            'view_state': view_state,
            'report_id': report_id,
            'login_user_id': login_user,
            'data_json': data_raw,
            'entries': entries,
        }

    def _parse_un_body(self, un_body):
        """
        解析 data.unBody（已填的计划外任务数组）。
        每行的 rs/es/ms/is 字段形如 [[day, value], ...]，按 day 索引填回长度 7 的数组。
        rs=rate, es=effort(hour), ms=remark, is=issue（来自 unplannedTask.js 的 unType + 历史命名）

        ASSUMED-1: unBody 行字段名沿用 RDM 的 r/e/m/i 简写（rs/es/ms/is）。fixture 里 unBody 是空数组，
                   无法 100% 验证。若实测对不上，需对照非空 fixture 调整字段名。
        """
        entries = []
        if not isinstance(un_body, list):
            return entries

        for row in un_body:
            if not isinstance(row, dict):
                continue
            tid = row.get('id') or row.get('taskId') or ''
            if not tid:
                continue

            hours = [0.0] * 7
            rates = [None] * 7

            for day_val in row.get('es', []) or []:
                try:
                    d = int(day_val[0]); v = float(day_val[1])
                    if 0 <= d < 7:
                        hours[d] = v
                except Exception:
                    pass
            for day_val in row.get('rs', []) or []:
                try:
                    d = int(day_val[0])
                    raw = day_val[1]
                    if raw == '' or raw is None:
                        continue
                    v = int(float(raw))
                    if 0 <= d < 7:
                        rates[d] = v
                except Exception:
                    pass

            entries.append({
                'task_id': tid,
                'hours': hours,
                'completion_rates': rates,
            })
        return entries

    # ----- 按月查询已填工时 -----
    def get_month_existing(self, year_month: str, task_id: str = None):
        """
        获取整个自然月已填工时。

        参数：year_month = "2026-06"
        返回：{date_str: {hour, rate}, ...}

        逻辑：
        1. 解析 year_month，计算当月第一天和最后一天
        2. 当 task_id 不为 None：
           a. 优先调 get_daily_report(task_id)（单次获取该任务全量历史）
           b. 若 dailyReport 成功且有数据 → 按月份过滤后返回
           c. 若 dailyReport 失败/无数据 → fallback 到 workLogView.jsf（步骤 3）
        3. 当 task_id 为 None 或 dailyReport fallback：
           a. 找出当月覆盖的所有自然周（周一），通常 4-6 个
           b. 对每个周一调用 get_week_existing(week_monday)
           c. 将返回的 7 天数组按日期拆分，合并为 {date_str: {hour, rate}} 字典
           d. 月初月末跨月周只取当月日期范围内的数据
           e. 单周失败不中断整月——记录日志，继续下一周
        4. 所有数据源（dailyReport + 所有周）都失败时，抛出 RuntimeError
           （视为会话过期）
        """
        try:
            year, month = map(int, year_month.split('-'))
        except (ValueError, AttributeError):
            raise ValueError(
                f"参数 year_month 格式错误，应为 YYYY-MM，收到: {year_month}"
            )

        if month < 1 or month > 12:
            raise ValueError(f"参数 year_month 月份无效: {year_month}")

        # 当月第一天和最后一天
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)

        # ---- Phase 2b: 优先走 dailyReport.jsf（task_id 维度）----
        daily_report_used = False
        daily_data = None
        if task_id:
            try:
                daily_data = self.get_daily_report(task_id)
                if daily_data:
                    daily_report_used = True
                    log.info(
                        "[OK] dailyReport 获取 %d 条记录 task=%s",
                        len(daily_data), task_id,
                    )
            except Exception as e:
                log.warning(
                    "[X] dailyReport 获取失败 task=%s: %s，fallback 到 "
                    "workLogView.jsf", task_id, e,
                )

        # 如果 dailyReport 拿到了数据，先填入结果
        result = {}
        if daily_report_used and daily_data:
            for date_str, data in daily_data.items():
                try:
                    d = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    continue
                # 只取当月日期
                if d.year != year or d.month != month:
                    continue
                result[date_str] = {
                    'hour': data.get('hour', 0.0),
                    'rate': data.get('rate', 0),
                }

        # ---- workLogView.jsf 路径（task_id=None 或 dailyReport fallback）----
        if not daily_report_used:
            # 覆盖当月所有自然周（周一~周日）
            start_monday = first_day - timedelta(days=first_day.weekday())
            end_monday = last_day - timedelta(days=last_day.weekday())

            total_weeks = 0
            failed_weeks = 0

            current_monday = start_monday
            while current_monday <= end_monday:
                total_weeks += 1
                monday_str = current_monday.strftime("%Y-%m-%d")
                try:
                    week_data = self.get_week_existing(monday_str)
                    for entry in week_data.get('entries', []):
                        e_task_id = entry.get('task_id', '')
                        if task_id and e_task_id != task_id:
                            continue
                        hours = entry.get('hours', [0.0] * 7)
                        rates = entry.get('completion_rates',
                                          [None] * 7)
                        for day_idx in range(7):
                            day_date = (current_monday
                                        + timedelta(days=day_idx))
                            # 只取当月日期，跨月周裁边
                            if (day_date.year != year
                                    or day_date.month != month):
                                continue
                            day_str = day_date.strftime("%Y-%m-%d")
                            hour = (hours[day_idx]
                                    if day_idx < len(hours)
                                    else 0.0)
                            rate_raw = (
                                rates[day_idx]
                                if day_idx < len(rates)
                                else None
                            )
                            rate_val = (int(rate_raw)
                                        if rate_raw is not None
                                        else 0)

                            if day_str in result:
                                # 多任务聚合：工时累加，进度取最大值
                                result[day_str]['hour'] += hour
                                result[day_str]['rate'] = max(
                                    result[day_str]['rate'], rate_val
                                )
                            else:
                                result[day_str] = {
                                    'hour': hour,
                                    'rate': rate_val,
                                }
                except Exception as e:
                    failed_weeks += 1
                    log.warning(
                        "[X] get_month_existing: 获取周 %s 失败: %s",
                        monday_str, e,
                    )

                current_monday += timedelta(days=7)

            if total_weeks > 0 and failed_weeks == total_weeks:
                raise RuntimeError("RDM 会话已过期，请重新登录")

        return result

    # ----- 单任务单天提交（entity.jsf → taskForm:save 路径）-----
    def submit_day(self, task_id: str, name: str, day_index: int, date: str,
                   hour: float, completion_rate, week_start: str):
        """
        通过 entity.jsf → taskForm:save 提交单任务单天工时。

        改动摘要（2026-06-23）：
        - 从 workLogView.jsf → saveLog（需要 _unplannedInfo 编码）改为
          entity.jsf → taskForm:save（简单 key=value form）
        - 字段映射参考 HAR Entry #4：report_action_date / report_rate /
          report_in_work / report_end_date / report_remain_work / operate_remark /
          report_question
        - 响应为 XML partial response，不再用 loginForm/viewExpired 黑名单逻辑
        - P2 加固：ViewState 过期自动重新登录 + 重试 1 次（适配 XML 响应）
        - P0 加固：app.debug=True 时输出完整请求/响应日志

        返回 {'success': bool, 'message': str}
        """
        for attempt in range(2):  # P2：最多 2 次（首次 + 1 次 ViewState 过期重试）
            try:
                # 1. GET entity.jsf 拿 ViewState + container_id
                ctx = self.get_entity_page(task_id)

                if not ctx.get('view_state'):
                    return {'success': False,
                            'message': '获取页面 ViewState 失败，请重试'}

                # 2. 构造简单 form（参考 HAR Entry #4 真实提交流程）
                rate_str = ''
                if completion_rate is not None:
                    rate_str = str(int(completion_rate))

                form = {
                    'AJAXREQUEST': ctx['container_id'],
                    'taskForm': 'taskForm',
                    'taskForm:save': 'taskForm:save',
                    'report_action_date': date,
                    'report_rate': rate_str,
                    'report_in_work': _format_hour(hour),
                    'report_end_date': '',
                    'report_remain_work': '',
                    'operate_remark': '',
                    'report_question': '',
                    'objectId': task_id,
                    'taskId': task_id,
                    'workflowType': 'TSK',
                    'action': '1',
                    # HAR 中出现的空字段（保持兼容）
                    'ueditor_image_urls': '',
                    'milestoneDate': '',
                    'formerDate': '',
                    'report_id': '',
                    'javax.faces.ViewState': ctx['view_state'],
                }
                headers = {
                    'Faces-Request': 'partial/ajax',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                }

                # P0 加固：debug 模式下输出完整 POST URL、请求头、form body
                if app.debug:
                    post_url = f"{self.base_url}/pages/task/entity.jsf"
                    log.debug("[DEBUG] submit_day POST URL: %s", post_url)
                    log.debug("[DEBUG] submit_day request headers: %s",
                              json.dumps(headers, ensure_ascii=False))
                    log.debug("[DEBUG] submit_day form data: %s",
                              json.dumps(form, ensure_ascii=False, default=str))

                # 3. POST entity.jsf
                r = self._request(
                    'POST',
                    '/pages/task/entity.jsf',
                    data=form, headers=headers,
                )

                # P0 加固：debug 模式下输出完整响应
                if app.debug:
                    log.debug("[DEBUG] submit_day HTTP status: %s", r.status_code)
                    log.debug("[DEBUG] submit_day response headers: %s",
                              dict(r.headers))
                    log.debug("[DEBUG] submit_day response body (前 2000 字符):\n%s",
                              (r.text or '')[:2000])

                # 4. 失败模式判断
                if r.status_code >= 500:
                    return {'success': False, 'message': 'RDM 服务异常，请稍后重试'}
                if r.status_code != 200:
                    return {'success': False,
                            'message': f'RDM 写入失败：HTTP {r.status_code}'}

                text = r.text or ''

                # P2 加固：ViewState 过期检测（entity.jsf XML 响应中也可能出现）
                if 'viewExpired' in text:
                    if attempt == 0:
                        if app.debug:
                            log.debug("[DEBUG] submit_day: viewExpired 检测到，"
                                      "自动重新登录并重试")
                        login_result = self.login(self.username, self._password)
                        if not login_result.get('success'):
                            return {'success': False,
                                    'message': '会话已过期，自动重登失败，请刷新重试'}
                        continue  # 重新进入循环，GET 新 ViewState 并重试提交
                    return {'success': False, 'message': '会话已过期，请刷新重试'}

                # TODO: entity.jsf 精确成功/失败标记待真实验证确认
                # 当前判断：XML 响应 + HTTP 200 + 无 viewExpired → 成功
                # XML 中可能的错误标记（待验证）：
                #   - <partial-response><error>...</error></partial-response>
                #   - <span class="error">...</span>
                # 若后续发现误判，在此处添加对应检测逻辑

                return {'success': True, 'message': '提交成功'}

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout):
                return {'success': False, 'message': 'RDM 写入失败：网络异常'}
            except Exception as e:
                log.exception("[X] submit_day error")
                return {'success': False, 'message': f'RDM 写入失败：{str(e)}'}


# ===========================================================================
# 模块级 clients dict（保持 v1 session 模型，CLAUDE.md 'session trap' 段已说明）
# ===========================================================================

clients = {}

def get_client():
    """获取当前用户的 RDMClient；未登录或 Flask 重启 → None"""
    username = session.get('username')
    if username and username in clients:
        return clients[username]
    return None


# ===========================================================================
# 节假日缓存（中国法定节假日 + 调休，来源 timor.tech 免费 API）
# ===========================================================================
# 双层缓存：内存（请求间共享）+ 文件（JSON，跨重启持久化，TTL 24h）
# INSPUR-32：节假日数据文件持久化，服务重启后不丢失
# ===========================================================================

_holiday_cache = {}
_holiday_cache_lock = threading.Lock()
_holiday_session = None


def _get_holiday_http():
    """获取节假日 API 专用 HTTP session（绕过系统代理，与 RDMClient 一致）"""
    global _holiday_session
    if _holiday_session is None:
        _holiday_session = requests.Session()
        _holiday_session.trust_env = False
        _holiday_session.headers.update({
            'User-Agent': 'gongshi-holiday/1.0',
        })
    return _holiday_session


def _get_holiday_cache_path(year: str) -> str:
    """返回节假日缓存文件路径 cache/holidays_{year}.json"""
    return os.path.join('cache', f'holidays_{year}.json')


def _load_holiday_cache_file(year: str) -> dict | None:
    """
    从文件读取节假日缓存。

    返回 holidays dict，以下情况返回 None：
    - 文件不存在
    - JSON 解析失败（损坏）
    - TTL 过期（默认 24h）

    INSPUR-32：缓存文件过期或损坏时自动重新同步
    """
    path = _get_holiday_cache_path(year)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, Exception):
        log.warning("[X] 节假日缓存文件损坏 year=%s，将重新拉取", year)
        return None

    expires_at = data.get('expires_at', '')
    if expires_at:
        try:
            expire_time = datetime.fromisoformat(expires_at)
            if datetime.now() >= expire_time:
                log.info("[OK] 节假日缓存已过期 year=%s，将重新拉取", year)
                return None
        except Exception:
            return None

    holidays = data.get('holidays')
    if not isinstance(holidays, dict):
        return None

    return holidays


def _write_holiday_cache_file(year: str, holidays: dict):
    """
    写入节假日缓存文件。

    INSPUR-32：确保 cache/ 目录存在，JSON 格式存储。
    """
    cache_dir = 'cache'
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    now = datetime.now()
    expires = now + timedelta(hours=24)
    cache_data = {
        'cached_at': now.isoformat(),
        'expires_at': expires.isoformat(),
        'year': year,
        'count': len(holidays),
        'holidays': holidays,
    }

    path = _get_holiday_cache_path(year)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 节假日缓存已写入 year={year} 共 {len(holidays)} 条")


def _fetch_holidays(year: str) -> dict:
    """从 timor.tech 拉取指定年份中国节假日数据，失败返回空 dict"""
    try:
        s = _get_holiday_http()
        r = s.get(
            f'https://timor.tech/api/holiday/year/{year}', timeout=10
        )
        data = r.json()
        if data.get('code') == 0:
            holidays = data.get('holiday', {})
            print(f"[OK] 节假日数据获取成功 year={year} 共 {len(holidays)} 条")
            return holidays
        else:
            log.warning("[X] 节假日 API 返回异常 code=%s", data.get('code'))
    except Exception as e:
        log.warning("[X] 节假日 API 请求失败 year=%s: %s", year, e)
    return {}


# ===========================================================================
# Flask 路由
# ===========================================================================

@app.before_request
def _intercept_unauth_api():
    """
    /api/* 的统一未登录 + 未激活拦截。

    登录检查（返回 200）：
      - /api/login、/api/logout 不拦截
      - 其余 /api/*：未登录 → {success:false, message:'未登录'}

    激活检查（返回 403）：
      - /api/license/* 不拦截（激活流程本身需要访问）
      - 其余 /api/*：未激活 → {success:false, message:'未激活', need_activate:true}
    """
    p = request.path
    if not p.startswith('/api/'):
        return None
    if p in ('/api/login', '/api/logout', '/api/version'):
        return None
    if p.startswith('/api/rdm-config'):
        return None

    # ---- 登录检查 ----
    if get_client() is None:
        return jsonify({'success': False, 'message': '未登录'}), 200

    # ---- 激活检查（License 和 Update 相关 API 豁免）----
    if not p.startswith('/api/license/') and not p.startswith('/api/update/') and p != '/api/system-info':
        is_active, _ = check_activated(session.get('username', ''))
        if not is_active:
            return jsonify({
                'success': False,
                'message': '未激活',
                'need_activate': True,
            }), 403

    return None


@app.route('/')
def index():
    """首页：已登录+已激活跳 dashboard；已登录+未激活跳 activate；否则登录页"""
    if 'logged_in' in session and session.get('username') in clients:
        is_active, _ = check_activated(session.get('username', ''))
        if not is_active:
            return redirect(url_for('activate_page'))
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/activate')
def activate_page():
    """License 激活页面：未登录跳 /"""
    if 'logged_in' not in session or session.get('username') not in clients:
        return redirect(url_for('index'))
    return render_template('activate.html', username=session.get('username'))


@app.route('/dashboard')
def dashboard():
    """主表页面壳：未登录跳 /；未激活跳 /activate"""
    if 'logged_in' not in session or session.get('username') not in clients:
        return redirect(url_for('index'))
    is_active, _ = check_activated(session.get('username', ''))
    if not is_active:
        return redirect(url_for('activate_page'))
    return render_template('dashboard.html', username=session.get('username'))


@app.route('/api/login', methods=['POST'])
def api_login():
    """登录接口"""
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名或密码不能为空'})

    client = RDMClient()
    result = client.login(username, password)

    if result.get('success'):
        session['logged_in'] = True
        session['username'] = username
        clients[username] = client
        print(f"[OK] 用户登录成功: {username}")
        return jsonify({'success': True, 'username': username})

    print(f"[X] 用户登录失败: {username} - {result.get('message')}")
    return jsonify({'success': False,
                    'message': result.get('message', '登录失败')})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """登出（始终成功）"""
    username = session.get('username')
    if username and username in clients:
        del clients[username]
    session.clear()
    print(f"[OK] 用户登出: {username or '(unknown)'}")
    return jsonify({'success': True})


@app.route('/api/tasks', methods=['GET'])
def api_tasks():
    """拉取我的任务（缓存优先；?refresh=true 强制重新抓取）"""
    client = get_client()
    try:
        force_refresh = request.args.get('refresh') == 'true'

        if not force_refresh:
            cache = client._load_cache()
            if cache:
                print(f"[OK] 缓存命中 {len(cache['tasks'])} 条任务 user={client.username}")
                return jsonify({'success': True, 'tasks': cache['tasks'], 'cached': True, 'cached_at': cache.get('cached_at', '')})

        tasks = client.get_my_tasks_http()
        client._write_cache(tasks)
        print(f"[OK] 拉取任务 {len(tasks)} 条 user={client.username}")
        return jsonify({'success': True, 'tasks': tasks, 'cached': False})
    except Exception as e:
        log.exception("[X] /api/tasks failed")
        return jsonify({'success': False,
                        'message': f'任务加载失败：{str(e)}'})


@app.route('/api/timesheet', methods=['GET'])
def api_timesheet():
    """按周回填已存在工时"""
    week_start = (request.args.get('week_start') or '').strip()
    if not week_start:
        return jsonify({'success': False, 'message': '缺少参数 week_start'})

    try:
        week_start = normalize_to_monday(week_start)
    except ValueError:
        return jsonify({'success': False,
                        'message': '参数 week_start 格式错误，应为 YYYY-MM-DD'})

    client = get_client()
    try:
        ctx = client.get_week_existing(week_start)
        print(f"[OK] 回填查询 week={week_start} 已填任务 {len(ctx['entries'])} 条")
        return jsonify({
            'success': True,
            'week_start': week_start,
            'tasks': ctx['entries'],
        })
    except Exception as e:
        log.exception("[X] /api/timesheet failed")
        return jsonify({'success': False,
                        'message': f'回填查询失败：{str(e)}'})


@app.route('/api/submit-day', methods=['POST'])
def api_submit_day():
    """单任务单天提交"""
    data = request.get_json(silent=True) or {}

    # 字段校验
    week_start = (data.get('week_start') or '').strip()
    task_id = (data.get('task_id') or '').strip()
    name = (data.get('name') or '').strip()
    day_index = data.get('day_index')
    date = (data.get('date') or '').strip()
    hour = data.get('hour')
    completion_rate = data.get('completion_rate', None)

    if not week_start or not task_id or not date:
        return jsonify({'success': False, 'message': '字段非法：缺少必填字段'})

    try:
        week_start = normalize_to_monday(week_start)
    except ValueError:
        return jsonify({'success': False,
                        'message': '字段非法：week_start 格式错误'})

    if not isinstance(day_index, int) or not (0 <= day_index <= 6):
        return jsonify({'success': False,
                        'message': '字段非法：day_index 必须为 0-6 整数'})

    try:
        hour_f = float(hour)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '字段非法：hour 必须为数字'})

    if hour_f <= 0 or hour_f > 24:
        return jsonify({'success': False,
                        'message': '字段非法：hour 必须 >0 且 <=24'})

    # 整数校验（INSPUR-23：工时仅接受整数）
    if hour_f != int(hour_f):
        return jsonify({'success': False,
                        'message': '字段非法：hour 必须为整数'})

    if completion_rate is not None:
        try:
            cr = int(completion_rate)
            if cr < 0 or cr > 100:
                return jsonify({'success': False,
                                'message': '字段非法：completion_rate 范围 0-100'})
            completion_rate = cr
        except (TypeError, ValueError):
            return jsonify({'success': False,
                            'message': '字段非法：completion_rate 必须为整数'})

    # ---- INSPUR-28：任务计划日期范围校验 ----
    plan_start = (data.get('plan_start') or '').strip()
    plan_end = (data.get('plan_end') or '').strip()
    if plan_start and date < plan_start:
        return jsonify({
            'success': False,
            'message': f'该日期({date})不在任务计划范围内（任务从 {plan_start} 开始）',
        })
    if plan_end and date > plan_end:
        return jsonify({
            'success': False,
            'message': f'该日期({date})不在任务计划范围内（任务已于 {plan_end} 结束）',
        })

    client = get_client()

    # ---- INSPUR-28：已填日期重复提交校验（防御性后端检查）----
    try:
        date_dt = datetime.strptime(date, "%Y-%m-%d")
        year_month = date_dt.strftime("%Y-%m")
        existing_before = client.get_month_existing(year_month, task_id=task_id)
        if existing_before.get(date, {}).get('hour', 0) > 0:
            return jsonify({
                'success': False,
                'message': f'该日期({date})已在RDM中填写过工时，不可重复提交',
            })
    except Exception as e:
        log.warning("[X] INSPUR-28 提交前已填校验失败（不阻断提交）: %s", e)
    result = client.submit_day(
        task_id=task_id,
        name=name,
        day_index=day_index,
        date=date,
        hour=hour_f,
        completion_rate=completion_rate,
        week_start=week_start,
    )

    if result.get('success'):
        print(f"[OK] 提交工时 task={task_id} day={day_index} hour={hour_f}")

        # ---- 提交后一致性核对（INSPUR-22）----
        verify_result = None
        try:
            date_dt = datetime.strptime(date, "%Y-%m-%d")
            year_month = date_dt.strftime("%Y-%m")
            import time as _time
            _time.sleep(0.3)  # 短暂等待 RDM 写入生效
            existing = client.get_month_existing(year_month, task_id=task_id)
            actual = existing.get(date, {'hour': 0.0, 'rate': 0})
            actual_hour = actual.get('hour', 0.0)
            actual_rate = actual.get('rate', 0)

            submitted_rate = completion_rate or 0
            hour_ok = abs(actual_hour - hour_f) < 0.01
            rate_ok = (actual_rate == submitted_rate)

            if hour_ok and rate_ok:
                verify_result = {'verified': True}
            else:
                diffs = []
                if not hour_ok:
                    diffs.append(
                        f"工时：提交 {_format_hour(hour_f)}h，"
                        f"RDM 实际 {_format_hour(actual_hour)}h"
                    )
                if not rate_ok:
                    diffs.append(
                        f"完成率：提交 {submitted_rate}%，"
                        f"RDM 实际 {actual_rate}%"
                    )
                verify_result = {'verified': False,
                                 'diff': '；'.join(diffs)}
                log.warning(
                    "[X] 一致性核对不匹配 date=%s task=%s: %s",
                    date, task_id, verify_result['diff'],
                )
        except Exception as e:
            log.warning("[X] 一致性核对异常: %s", e)
            verify_result = None  # 核对跳过，不阻断提交流程

        return jsonify({
            'success': True,
            'message': '提交成功',
            'task_id': task_id,
            'day_index': day_index,
            'verify': verify_result,
        })

    msg = result.get('message') or 'RDM 写入失败'
    print(f"[X] 提交工时失败 task={task_id} day={day_index}: {msg}")
    return jsonify({'success': False, 'message': msg})


@app.route('/api/timesheet-month', methods=['GET'])
def api_timesheet_month():
    """按月回填已存在工时"""
    year_month = (request.args.get('year_month') or '').strip()
    if not year_month:
        return jsonify({'success': False, 'message': '缺少参数 year_month'})

    try:
        year, month = map(int, year_month.split('-'))
        datetime(year, month, 1)  # 验证日期有效性
    except (ValueError, AttributeError):
        return jsonify({
            'success': False,
            'message': '参数 year_month 格式错误，应为 YYYY-MM',
        })

    task_id = (request.args.get('task_id') or '').strip() or None

    client = get_client()
    try:
        existing = client.get_month_existing(year_month, task_id=task_id)
    except RuntimeError:
        return jsonify({
            'success': False,
            'message': 'RDM 会话已过期，请重新登录',
        })
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)})
    except Exception as e:
        log.exception("[X] /api/timesheet-month failed")
        return jsonify({'success': False, 'message': f'查询失败：{str(e)}'})

    # 构造当月每一天的响应数据
    first_day = datetime(year, month, 1)
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

    days = []
    current = first_day
    while current <= last_day:
        day_str = current.strftime("%Y-%m-%d")
        weekday_idx = current.weekday()
        data = existing.get(day_str, {'hour': 0.0, 'rate': 0})
        days.append({
            'date': day_str,
            'weekday': WEEKDAY_NAMES[weekday_idx],
            'is_weekend': weekday_idx >= 5,
            'existing_hour': data['hour'],
            'existing_rate': data['rate'],
        })
        current += timedelta(days=1)

    print(
        f"[OK] 月查询 year_month={year_month} "
        f"task_id={task_id or '(全部)'} 共 {len(days)} 天"
    )
    return jsonify({
        'success': True,
        'year_month': year_month,
        'task_id': task_id,
        'days': days,
    })


@app.route('/api/task/<taskId>/team_logs', methods=['GET'])
def api_team_logs(taskId):
    """获取指定任务的全员执行日报"""
    if not taskId or not taskId.strip():
        return jsonify({'success': False, 'message': '缺少参数 taskId'})

    client = get_client()
    try:
        logs = client.get_team_logs(taskId.strip())
        print(f"[OK] 全员日报 task={taskId} 共 {len(logs)} 条")

        # 按人分组统计：每人工时总和 + 最后一条记录的完成率
        member_map = {}  # member_name -> {total_hour, entry_count, latest_date, latest_rate}
        for log in logs:
            name = log.get('member_name', '')
            if not name:
                continue
            if name not in member_map:
                member_map[name] = {'total_hour': 0.0, 'entry_count': 0, 'latest_date': '', 'latest_rate': 0}
            member_map[name]['total_hour'] += float(log.get('hour', 0) or 0)
            member_map[name]['entry_count'] += 1
            # 取日期最新的一条记录的完成率
            date_str = str(log.get('date', '') or '')
            if date_str > member_map[name]['latest_date']:
                member_map[name]['latest_date'] = date_str
                member_map[name]['latest_rate'] = float(log.get('rate', 0) or 0)

        stats = []
        for name, data in member_map.items():
            stats.append({
                'member_name': name,
                'total_hour': round(data['total_hour'], 1),
                'final_rate': data['latest_rate'],
                'entry_count': data['entry_count'],
            })
        # 按工时总和降序排列
        stats.sort(key=lambda x: x['total_hour'], reverse=True)

        return jsonify({
            'success': True,
            'task_id': taskId,
            'logs': logs,
            'count': len(logs),
            'stats': stats,
        })
    except RuntimeError:
        return jsonify({
            'success': False,
            'message': 'RDM 会话已过期，请重新登录',
        })
    except Exception as e:
        log.exception("[X] /api/task/%s/team_logs failed", taskId)
        return jsonify({
            'success': False,
            'message': f'获取全员日报失败：{str(e)}',
        })


@app.route('/api/holidays', methods=['GET'])
def api_holidays():
    """获取中国法定节假日和调休信息（来源 timor.tech）

    缓存层级（INSPUR-32）：
    1. 文件缓存（跨重启持久化，TTL 24h）
    2. 内存缓存（请求间共享，进程内有效）
    3. 网络拉取（fallback）

    ?year=2026 & refresh=true 强制重新拉取并刷新所有缓存层
    """
    year = (request.args.get('year') or '').strip()
    if not year:
        year = str(datetime.now().year)
    force = request.args.get('refresh') == 'true'

    if not force:
        # 1) 文件缓存优先（INSPUR-32：服务重启后数据不丢失）
        cached = _load_holiday_cache_file(year)
        if cached:
            # 同步到内存缓存，避免后续请求重复读文件
            with _holiday_cache_lock:
                _holiday_cache[year] = cached
            return jsonify({
                'success': True,
                'holidays': cached,
                'count': len(cached),
                'cached': True,
                'source': 'file',
            })
        # 2) 内存缓存
        with _holiday_cache_lock:
            if year in _holiday_cache:
                mem = _holiday_cache[year]
                # 持久化到文件（上次可能是从网络拉取后仅存于内存）
                _write_holiday_cache_file(year, mem)
                return jsonify({
                    'success': True,
                    'holidays': mem,
                    'count': len(mem),
                    'cached': True,
                    'source': 'memory',
                })

    # 3) 网络拉取
    holidays = _fetch_holidays(year)
    if holidays:
        with _holiday_cache_lock:
            _holiday_cache[year] = holidays
        _write_holiday_cache_file(year, holidays)

    return jsonify({
        'success': True,
        'holidays': holidays,
        'count': len(holidays),
        'cached': False,
        'source': 'network',
    })


# ===========================================================================
# License 激活 API
# ===========================================================================


@app.route('/api/license/sn', methods=['GET'])
def api_license_sn():
    """获取当前用户的 SN 码"""
    username = session.get('username', '')
    if not username:
        return jsonify({'success': False, 'message': '未登录'})
    sn = generate_sn(username)
    print(f"[OK] SN 生成 user={username} sn={sn}")
    return jsonify({'success': True, 'sn': sn, 'username': username})


@app.route('/api/license/info', methods=['GET'])
def api_license_info():
    """返回当前 License 激活信息"""
    is_active, info = check_activated(session.get('username', ''))
    # 不暴露完整 License 字符串，仅返回摘要信息
    result = {
        'success': True,
        'activated': is_active,
        'sn': info.get('sn', ''),
        'type': info.get('type', ''),
        'exp': info.get('exp'),
        'activated_at': info.get('activated_at', ''),
    }
    print(f"[OK] License 信息查询 activated={is_active}")
    return jsonify(result)


@app.route('/api/license/activate', methods=['POST'])
def api_license_activate():
    """
    License 激活接口。支持重复激活（同一用户用新 License 再次激活会覆盖旧记录）。

    请求体 JSON：
      - license: License 字符串（必填）

    SN 校验：激活时比对 License 中的 SN 是否与当前用户匹配，
    防止用户 A 的 License 被用户 B 使用。
    """
    data = request.get_json(silent=True) or {}
    license_str = (data.get('license') or '').strip()

    if not license_str:
        return jsonify({'success': False, 'message': '请输入 License'})

    # 1. 验证 License 签名 + 过期
    valid, payload, error = verify_license(license_str)
    if not valid:
        print(f"[X] License 激活失败: {error}")
        return jsonify({'success': False, 'message': error})

    # 2. SN 匹配校验（防止 License 跨用户使用）
    username = session.get('username', '')
    current_sn = generate_sn(username)
    license_sn = payload.get('sn', '')

    if current_sn != license_sn:
        print(f"[X] License 激活失败: SN 不匹配 "
              f"user_sn={current_sn} license_sn={license_sn}")
        return jsonify({
            'success': False,
            'message': '此 License 与当前用户不匹配，请确认 SN 码是否正确',
        })

    # 3. 写入激活状态
    status = activate(current_sn, license_str, payload)
    print(f"[OK] License 激活成功 user={username} "
          f"type={payload.get('type')} exp={payload.get('exp')}")
    return jsonify({
        'success': True,
        'message': '激活成功',
        'type': payload.get('type'),
        'exp': payload.get('exp'),
    })


# ===========================================================================
# 系统信息 API（版本 + License + 更新）
# ===========================================================================

@app.route('/api/system-info', methods=['GET'])
def api_system_info():
    """返回系统综合信息：版本号 + License 激活状态 + 更新检查结果。

    三个部分各独立容错：一个部分失败不影响其他部分的展示。
    """
    # 1. 版本号
    try:
        version = _read_app_version()
    except Exception as _e:
        log.warning("[!] 版本号读取失败: %s", _e)
        version = '0.0.0'

    # 2. License 信息
    try:
        username = session.get('username', '')
        is_active, lic_info = check_activated(username)
        license_data = {
            'activated': is_active,
            'sn': lic_info.get('sn', ''),
            'type': lic_info.get('type', ''),
            'exp': lic_info.get('exp'),
            'activated_at': lic_info.get('activated_at', ''),
        }
    except Exception as _e:
        log.warning("[!] License 信息获取失败: %s", _e)
        license_data = {
            'activated': False,
            'sn': '',
            'type': '',
            'exp': None,
            'activated_at': '',
        }

    # 3. 更新信息（仅桌面模式，含下载状态）
    update_data = {'has_update': False}
    try:
        from _desktop_common import get_update_checker
        checker = get_update_checker()
        result = checker.get_last_check()
        if result:
            update_data = {
                'has_update': True,
                'version': result.get('version', ''),
                'release_notes': result.get('release_notes', ''),
                'download_url': result.get('download_url', ''),
            }
        # 合并下载/安装状态（下载中、已下载等）
        try:
            dl_status = checker.get_status()
            update_data['dl_status'] = dl_status
        except Exception:
            pass
    except Exception as _e:
        log.warning("[!] 更新信息获取失败: %s", _e)

    return jsonify({
        'success': True,
        'version': version,
        'license': license_data,
        'update': update_data,
    })


@app.route('/api/release-notes', methods=['GET'])
def api_release_notes():
    """返回发布日志（各版本变更说明），供前端 Release Note 弹窗使用。

    数据来自 GitHub Releases API，返回格式：
    [{version: "v1.0.2", changes: ["变更1", "变更2"], ...}]
    """
    try:
        from _desktop_common import get_update_checker
        checker = get_update_checker()
        notes = checker.get_all_release_notes()
        return jsonify({'success': True, 'release_notes': notes})
    except Exception as _e:
        log.warning("[!] Release Note 获取失败: %s", _e)
        return jsonify({'success': True, 'release_notes': []})


@app.route('/api/version', methods=['GET'])
def api_version():
    """返回当前版本号，无需登录"""
    return jsonify({'version': _read_app_version()})


# ===========================================================================
# 更新检查 API
# ===========================================================================

@app.route('/api/update/check', methods=['GET'])
def api_update_check():
    """返回更新信息。check_now=1 时主动检查，否则返回缓存。"""
    try:
        from _desktop_common import get_update_checker, _read_version
    except ImportError:
        return jsonify({'has_update': False})

    try:
        checker = get_update_checker()

        # 主动检查模式
        if request.args.get('check_now') == '1':
            current_version = _read_version()
            result = checker.check_update(current_version)
            if result:
                return jsonify(result)
            return jsonify({'has_update': False})

        # 返回缓存
        result = checker.get_last_check()
        if result:
            return jsonify(result)
    except Exception as _e:
        log.warning("[!] 更新检查失败: %s", _e)

    return jsonify({'has_update': False})


@app.route('/api/update/download', methods=['POST'])
def api_update_download():
    """触发异步下载最新版本安装包。需要登录但不需激活检查。"""
    try:
        from _desktop_common import get_update_checker, _get_data_dir
    except ImportError:
        return jsonify({'success': False, 'message': '桌面模式下才支持在线更新'})

    checker = get_update_checker()
    last = checker.get_last_check()
    if not last or not last.get('download_url'):
        return jsonify({'success': False, 'message': '无可用下载链接'})

    data_dir = _get_data_dir()
    updates_dir = os.path.join(data_dir, 'updates')
    checker.start_download(last['download_url'], updates_dir)
    return jsonify({'success': True, 'message': '开始下载'})


@app.route('/api/update/status', methods=['GET'])
def api_update_status():
    """查询下载进度。需要登录但不需激活检查。"""
    try:
        from _desktop_common import get_update_checker
    except ImportError:
        return jsonify({'downloading': False, 'progress_percent': 0, 'downloaded': False})

    checker = get_update_checker()
    return jsonify(checker.get_status())


@app.route('/api/update/install', methods=['POST'])
def api_update_install():
    """安装已下载的更新包。标记安装状态，等待前端调用 /api/update/restart。"""
    try:
        from _desktop_common import get_update_checker
    except ImportError:
        return jsonify({'success': False, 'message': '桌面模式下才支持在线更新'})

    checker = get_update_checker()
    success, msg = checker.install_update()
    return jsonify({'success': success, 'message': msg,
                    'install_status': checker.get_status().get('install_status', 'idle')})


@app.route('/api/update/restart', methods=['POST'])
def api_update_restart():
    """启动安装脚本并重启应用（Windows 平台）。"""
    try:
        from _desktop_common import get_update_checker
    except ImportError:
        return jsonify({'success': False, 'message': '桌面模式下才支持在线更新'})

    checker = get_update_checker()
    success, msg = checker.restart_and_install()
    if not success:
        return jsonify({'success': False, 'message': msg})

    # 注册一个延迟退出的回调，让响应先返回给前端
    @after_this_request
    def _schedule_exit(response):
        import threading
        def _delayed_exit():
            time.sleep(0.5)
            os._exit(0)
        threading.Thread(target=_delayed_exit, daemon=True).start()
        return response

    return jsonify({'success': True, 'message': msg})


# ===========================================================================
# RDM 地址配置 API（无需登录，供前端登录页使用）
# ===========================================================================


@app.route('/api/rdm-config', methods=['GET', 'POST'])
def api_rdm_config():
    """
    RDM 地址配置接口。

    GET  — 获取当前 RDM 地址
    POST — 保存 RDM 地址（需 JSON body: {"url": "http://..."}）
    """
    if request.method == 'GET':
        url = rdm_config.get_rdm_base_url()
        return jsonify({'success': True, 'url': url})
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        url = (data.get('url') or '').strip()
        if not url:
            return jsonify({'success': False, 'message': 'RDM 地址不能为空'})
        # 简单的 URL 格式校验
        if not url.startswith('http://') and not url.startswith('https://'):
            return jsonify({'success': False, 'message': 'RDM 地址必须以 http:// 或 https:// 开头'})
        rdm_config.set_rdm_base_url(url)
        print(f"[OK] RDM 地址已更新: {url}")
        return jsonify({'success': True, 'url': url, 'message': 'RDM 地址已保存'})


@app.route('/api/rdm-config/reset', methods=['POST'])
def api_rdm_config_reset():
    """恢复默认 RDM 地址"""
    url = rdm_config.reset_rdm_base_url()
    return jsonify({'success': True, 'url': url, 'message': '已恢复默认 RDM 地址'})


@app.route('/api/rdm-config/check', methods=['POST'])
def api_rdm_config_check():
    """
    真实连通性检测：向当前配置的 RDM 地址发送 HTTP GET 请求。

    请求体 JSON（可选）：
      - url: 要检测的 URL（不传则使用已保存的 RDM 地址）

    返回：
      - success: 连通性检测结果（true/false）
      - reachable: 服务可达
      - message: 人类可读状态描述
      - status_code: HTTP 状态码（可达时）
      - elapsed_ms: 响应耗时（毫秒）
    """
    data = request.get_json(silent=True) or {}
    target_url = (data.get('url') or '').strip()
    if not target_url:
        target_url = rdm_config.get_rdm_base_url()

    if not target_url.startswith('http://') and not target_url.startswith('https://'):
        return jsonify({
            'success': False,
            'reachable': False,
            'message': '无效的 RDM 地址',
        })

    import time as _time
    try:
        start = _time.time()
        # 创建一个不带登录态的全新 session，仅用于连通性探测
        probe = requests.Session()
        probe.trust_env = False
        probe.headers.update({
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
        })
        r = probe.get(target_url, timeout=5)
        elapsed_ms = round((_time.time() - start) * 1000)
        return jsonify({
            'success': True,
            'reachable': True,
            'message': f'RDM 服务运行正常（HTTP {r.status_code}，响应 {elapsed_ms}ms）',
            'status_code': r.status_code,
            'elapsed_ms': elapsed_ms,
        })
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        elapsed_ms = round((_time.time() - start) * 1000)
        return jsonify({
            'success': True,
            'reachable': False,
            'message': f'无法连接 RDM 服务，请检查地址和网络（超时 {elapsed_ms}ms）',
            'elapsed_ms': elapsed_ms,
        })
    except Exception as e:
        return jsonify({
            'success': True,
            'reachable': False,
            'message': f'连通性检测异常: {str(e)}',
        })


# ===========================================================================
# 入口
# ===========================================================================

if __name__ == '__main__':
    # P2 加固：始终启用 DEBUG 日志（debug=True 总是开启，在 app.run 之前设置）
    log.setLevel(logging.DEBUG)

    print("=" * 60)
    print("RDM 工时填报系统 v2")
    print("=" * 60)
    print("启动服务器...")
    print("访问地址: http://localhost:5000")
    print("按 Ctrl+C 停止服务器")
    print()

    app.run(debug=True, host='0.0.0.0', port=5000)
