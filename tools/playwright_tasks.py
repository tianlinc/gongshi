#!/usr/bin/env python3
"""
用 Playwright 无头浏览器从 RDM 获取我的任务列表。
流程：Python 登录 → 拿 cookie → 注入浏览器 → 点 radio → 抓 DOM
"""
import argparse
import getpass
import sys
import time
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64

BASE = "http://10.111.36.3:2029"


def encrypt(text):
    key = b"abcdefgabcdefg12"
    cipher = AES.new(key, AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
    return base64.b64encode(encrypted).decode('utf-8')


def _request_with_retry(ses, method, url, **kwargs):
    """带重试的 HTTP 请求（处理 RDM 偶发 connection reset）"""
    kwargs.setdefault('timeout', 15)
    last_exc = None
    for attempt in range(3):
        try:
            return ses.request(method, url, **kwargs)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            last_exc = e
            if attempt < 2:
                print(f"  [retry] {method} {url} (attempt {attempt+2}/3)")
                time.sleep(1.5)
                continue
            raise
    raise last_exc  # type: ignore


def login(username, password):
    """Python 登录 RDM，返回 {cookies, jsessionid}"""
    ses = requests.Session()
    ses.headers['User-Agent'] = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    _request_with_retry(ses, 'GET', f"{BASE}/index.jsp")

    eu = encrypt(base64.b64encode(username.encode('utf-8')).decode('utf-8'))
    ep = encrypt(base64.b64encode(password.encode('utf-8')).decode('utf-8'))

    r = _request_with_retry(ses, 'POST', f"{BASE}/j_security_check", data={
        "j_username": eu, "j_password": ep, "isExpires": "1",
        "sessionIndex": "", "BROWSER_VERSION": "1", "REMOTE_LANGUAGE": "zh-cn",
    }, allow_redirects=True)

    if "error=true" in r.url or ("loginForm" in r.text and len(r.text) < 15000):
        print(f"[X] 登录失败")
        sys.exit(1)
    print(f"[OK] 登录成功")

    cookies = ses.cookies.get_dict()
    print(f"     JSESSIONID={cookies.get('JSESSIONID', '?')[:20]}...")
    return cookies


def scrape_tasks(cookies):
    """用 Playwright 加载我的任务页面，切 scope 抓任务列表"""
    from playwright.sync_api import sync_playwright

    # 转成 Playwright cookie 格式
    pw_cookies = [
        {"name": k, "value": v, "domain": "10.111.36.3", "path": "/"}
        for k, v in cookies.items()
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
        )
        context.add_cookies(pw_cookies)
        page = context.new_page()

        all_tasks = {}

        for cate, label in [("0", "我负责"), ("22", "我参与")]:
            print(f"\n--- cate={cate} ({label}) ---")
            # 先 GET 拿到完整页面（含 ViewState + radio buttons）
            page.goto(f"{BASE}/pages/task/list/myTask.jsf", timeout=20000)
            page.wait_for_load_state("networkidle")

            # 点击对应的 radio button 触发 chooseType → A4J
            radio_id = "myRecive" if cate == "0" else "myReciveActor"
            radio = page.wait_for_selector(f"#{radio_id}", timeout=10000)
            radio.click()

            # 等 A4J 刷新：body-row tr 出现 或 超时
            try:
                page.wait_for_selector("tr.body-row", timeout=8000)
            except Exception:
                print(f"  (无 body-row 出现，可能 {label} 列表为空)")
                # 截图供调试
                page.screenshot(path=f"tools/_diag_pw_{label}.png")
                continue

            # 抓取所有任务行
            rows = page.query_selector_all("tr.body-row")
            print(f"  抓到 {len(rows)} 行")
            for row in rows:
                status = row.get_attribute("status") or ""
                tid = row.get_attribute("id") or ""
                tds = row.query_selector_all("td")

                name = ""
                project = ""
                project_id = ""

                if len(tds) > 5:
                    a = tds[5].query_selector("a")
                    name = (a.inner_text() if a else tds[5].inner_text()).strip()
                if len(tds) > 7:
                    a = tds[7].query_selector("a")
                    project = (a.inner_text() if a else tds[7].inner_text()).strip()
                    if a:
                        onclick = a.get_attribute("onclick") or ""
                        import re
                        m = re.search(r"openEntity\(['\"]([^'\"]+)['\"]", onclick)
                        if m:
                            project_id = m.group(1)

                print(f"  [{status}] {tid[:30]}...  {name[:50]}  |  {project[:40]}")

                if tid not in all_tasks:
                    all_tasks[tid] = {
                        "task_id": tid,
                        "name": name,
                        "project": project,
                        "project_id": project_id,
                        "status_code": status,
                        "source": label,
                    }
                else:
                    all_tasks[tid]["source"] = "both"

            page.screenshot(path=f"tools/_diag_pw_{label}.png")

        browser.close()

    return list(all_tasks.values())


def main():
    parser = argparse.ArgumentParser(description="Playwright RDM 任务列表抓取")
    parser.add_argument("--user", "-u", help="RDM 用户名")
    parser.add_argument("--pass", "-p", dest="password", help="RDM 密码")
    args = parser.parse_args()

    username = args.user or input("用户名: ").strip()
    password = args.password or getpass.getpass("密码: ").strip()
    if not username or not password:
        print("[X] 账号密码不能为空")
        sys.exit(1)

    # 1) Python 登录
    cookies = login(username, password)

    # 2) Playwright 抓任务
    tasks = scrape_tasks(cookies)

    # 3) 输出
    import json
    print(f"\n=== 合计 {len(tasks)} 个任务 ===")
    print(json.dumps(tasks, ensure_ascii=False, indent=2))

    # 保存结果
    with open("tools/_tasks_result.json", "w", encoding="utf-8") as f:
        json.dump({"success": True, "tasks": tasks}, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存到 tools/_tasks_result.json")


if __name__ == "__main__":
    main()
