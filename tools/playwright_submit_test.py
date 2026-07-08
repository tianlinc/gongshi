#!/usr/bin/env python3
"""Playwright 提交测试：真实模拟用户操作提交流程"""
import sys, time, base64
from pathlib import Path
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

BASE = "http://10.111.36.3:2029"
TASK_ID = "2303bf8f-5937-49d7-9946-7dba5dfd95cf"
TASK_NAME = "InManage"
WEEK_START = "2026-06-01"
HOUR, RATE = 8, 2
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def encrypt(t):
    c = AES.new(b"abcdefgabcdefg12", AES.MODE_ECB)
    return base64.b64encode(c.encrypt(pad(t.encode(), AES.block_size))).decode()

def login(u, p):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for _ in range(3):
        try:
            s.get(f"{BASE}/index.jsp", timeout=15)
            eu = encrypt(base64.b64encode(u.encode()).decode())
            ep = encrypt(base64.b64encode(p.encode()).decode())
            r = s.post(f"{BASE}/j_security_check", data={
                "j_username": eu, "j_password": ep, "isExpires": "1",
                "sessionIndex": "", "BROWSER_VERSION": "1", "REMOTE_LANGUAGE": "zh-cn",
            }, allow_redirects=True, timeout=15)
            break
        except Exception as e:
            if _ < 2: time.sleep(1.5); continue; raise
    if "error=true" in r.url or ("loginForm" in r.text and len(r.text) < 15000):
        print("[X] login failed"); sys.exit(1)
    print("[OK] logged in")
    return s.cookies.get_dict()

def run(cookies):
    from playwright.sync_api import sync_playwright
    pw = [{"name": k, "value": v, "domain": "10.111.36.3", "path": "/"} for k, v in cookies.items()]
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA)
        ctx.add_cookies(pw)
        pg = ctx.new_page()

        # 1) Open workLogView - default page first
        pg.goto(f"{BASE}/pages/myspace/log/workLogView.jsf", timeout=20000)
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(2000)  # extra time for JS init
        pg.screenshot(path="tools/_diag_01_default.png")

        # Check key elements
        checks = {}
        for name, sel in [
            ("report_action_date", "#report_action_date"),
            ("edit_btn", "#edit"),
            ("unplannedTab", "#unplannedTab"),
            ("outerDiv", "#outerDiv"),
            ("save_btn", "[id='operate:saveLog']"),
            ("unplanedDate", "#unplanedDate"),
        ]:
            el = pg.query_selector(sel)
            checks[name] = "FOUND" if el else "MISSING"
        print(f"  elements: {checks}")

        # Check body text more carefully (skip script tags)
        body_txt = pg.evaluate("""
            (function() {
                var clone = document.body.cloneNode(true);
                var scripts = clone.querySelectorAll('script');
                scripts.forEach(function(s) { s.remove(); });
                return clone.innerText.substring(0, 500);
            })()
        """)
        print(f"  body(no script): {body_txt[:300]}")

        # Try to find the date field and set it
        date_el = pg.query_selector("#report_action_date")
        if date_el:
            print(f"  date current value: {date_el.input_value()}")
            # Use real keyboard input
            date_el.click()
            date_el.fill("")
            date_el.type(WEEK_START, delay=50)
            pg.wait_for_timeout(500)
            date_el.press("Enter")
            pg.wait_for_timeout(2000)
            pg.wait_for_load_state("networkidle")
            print(f"  date after typing: {date_el.input_value()}")
        pg.screenshot(path="tools/_diag_02_date_changed.png")

        # Diagnostic: table structure
        diag = pg.evaluate("""
            (function() {
                var r = {};
                var t = document.getElementById('unplannedTab');
                if (!t) return JSON.stringify({error:'no table'});
                var trs = t.querySelectorAll('tr');
                r.rowCount = trs.length;
                if (trs.length > 0) {
                    r.hdrNames = [];
                    (trs[0].querySelectorAll('th, td') || []).forEach(function(c) {
                        r.hdrNames.push(c.getAttribute('name') || '(none)');
                    });
                }
                r.editRowIdx = -1;
                for (var i = 0; i < trs.length; i++) {
                    if (trs[i].getAttribute('isEdit') === 'Y') {
                        r.editRowIdx = i;
                        r.editNames = [];
                        (trs[i].querySelectorAll('td') || []).forEach(function(c) {
                            r.editNames.push(c.getAttribute('name') || '(none)');
                        });
                    }
                }
                r.selDay = typeof selDay !== 'undefined' ? selDay : 'undef';
                return JSON.stringify(r);
            })()
        """)
        print(f"  unplannedTab: {diag}")

        pg.screenshot(path="tools/_diag_final.png")
        print("\nDone. Check screenshots in tools/_diag_*.png")
        b.close()

if __name__ == "__main__":
    creds = Path(__file__).parent / ".rdm_creds"
    if creds.exists():
        lines = creds.read_text().strip().splitlines()
        u, w = lines[0].strip(), lines[1].strip()
    else:
        import argparse, getpass
        p = argparse.ArgumentParser()
        p.add_argument("--user","-u"); p.add_argument("--pass","-p",dest="pw")
        a = p.parse_args()
        u = a.user or input("user: ").strip()
        w = a.pw or getpass.getpass("pass: ").strip()
    run(login(u, w))
