"""列出 workLogView 页面所有 input id，找到日期选择器"""
import time, base64
from pathlib import Path
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

BASE = "http://10.111.36.3:2029"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def enc(t):
    c = AES.new(b"abcdefgabcdefg12", AES.MODE_ECB)
    return base64.b64encode(c.encrypt(pad(t.encode(), AES.block_size))).decode()

creds = Path("tools/.rdm_creds")
lines = creds.read_text().strip().splitlines()
u, p = lines[0].strip(), lines[1].strip()

# Python login
s = requests.Session()
s.headers["User-Agent"] = UA
s.get(f"{BASE}/index.jsp")
eu = enc(base64.b64encode(u.encode()).decode())
ep = enc(base64.b64encode(p.encode()).decode())
s.post(f"{BASE}/j_security_check", data={
    "j_username": eu, "j_password": ep, "isExpires": "1",
    "sessionIndex": "", "BROWSER_VERSION": "1", "REMOTE_LANGUAGE": "zh-cn",
}, allow_redirects=True)

cookies = s.cookies.get_dict()

# Playwright
from playwright.sync_api import sync_playwright
pw = [{"name": k, "value": v, "domain": "10.111.36.3", "path": "/"} for k, v in cookies.items()]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA)
    ctx.add_cookies(pw)
    pg = ctx.new_page()

    # Try different URLs
    for url, label in [
        (f"{BASE}/pages/myspace/log/workLogView.jsf", "workLogView"),
        (f"{BASE}/pages/myspace/log/workLogList.jsf", "workLogList"),
        (f"{BASE}/pages/task/list/myTask.jsf", "myTask"),
    ]:
        print(f"\n=== {label} ({url}) ===")
        pg.goto(url, timeout=20000)
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(2000)

        # List ALL input ids
        inputs = pg.evaluate("""
            (function() {
                var ids = [];
                document.querySelectorAll('input').forEach(function(el) {
                    ids.push({id: el.id, name: el.name, type: el.type, val: (el.value||'').substring(0,30)});
                });
                return JSON.stringify(ids);
            })()
        """)
        inp_list = __import__('json').loads(inputs)
        for inp in inp_list:
            print(f"  id={inp['id']:30s} name={inp['name']:25s} type={inp['type']:10s} val={inp['val']}")

        # Also check iframes
        frames = pg.frames
        print(f"  frames: {len(frames)}")
        for f in frames[1:]:  # skip main frame
            print(f"    frame: {f.name} url={f.url[:80]}")

    b.close()
