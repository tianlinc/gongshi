"""通过导航路径访问 RDM，找 report_action_date"""
from pathlib import Path
import requests, base64, time, json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

BASE = "http://10.111.36.3:2029"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def enc(t):
    c = AES.new(b"abcdefgabcdefg12", AES.MODE_ECB)
    return base64.b64encode(c.encrypt(pad(t.encode(), AES.block_size))).decode()

creds = Path("tools/.rdm_creds")
u, p = creds.read_text().strip().splitlines()[:2]

s = requests.Session()
s.headers["User-Agent"] = UA
s.get(f"{BASE}/index.jsp")
s.post(f"{BASE}/j_security_check", data={
    "j_username": enc(base64.b64encode(u.encode()).decode()),
    "j_password": enc(base64.b64encode(p.encode()).decode()),
    "isExpires": "1", "sessionIndex": "", "BROWSER_VERSION": "1", "REMOTE_LANGUAGE": "zh-cn",
}, allow_redirects=True)

cookies = s.cookies.get_dict()
from playwright.sync_api import sync_playwright
pw = [{"name": k, "value": v, "domain": "10.111.36.3", "path": "/"} for k, v in cookies.items()]

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent=UA)
    ctx.add_cookies(pw)
    pg = ctx.new_page()

    # Go to main.do (home page after login)
    pg.goto(f"{BASE}/main.do", timeout=20000)
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(2000)

    # List ALL inputs on this page
    inp_json = pg.evaluate("""(function() {
        var r = [];
        document.querySelectorAll('input').forEach(function(el) {
            r.push({id: el.id, name: el.name || '', type: el.type, val: (el.value||'').substring(0,40)});
        });
        return JSON.stringify(r);
    })()""")
    for inp in json.loads(inp_json):
        if inp['id'] or inp['name'] or inp['type'] in ('text','date','button'):
            print(f"  {inp}")

    # Also search across all frames
    for frame in pg.frames:
        try:
            inp_json2 = frame.evaluate("""(function() {
                var r = [];
                document.querySelectorAll('input').forEach(function(el) {
                    r.push({id: el.id, type: el.type, val: (el.value||'').substring(0,40)});
                });
                return JSON.stringify(r);
            })()""")
            for inp in json.loads(inp_json2):
                if 'report_action' in inp['id'] or 'date' in inp['id'].lower():
                    print(f"  FRAME({frame.name}): {inp}")
        except: pass

    # Try to click "工作日志" link
    pg.screenshot(path="tools/_diag_main.png")
    try:
        pg.click("text=工作日志", timeout=5000)
        pg.wait_for_timeout(2000)
        pg.wait_for_load_state("networkidle")
        pg.screenshot(path="tools/_diag_worklog.png")
        print(f"\nURL after clicking 工作日志: {pg.url}")

        # Check all inputs again
        inp_json3 = pg.evaluate("""(function() {
            var r = [];
            document.querySelectorAll('input').forEach(function(el) {
                r.push({id: el.id, name: el.name || '', type: el.type, val: (el.value||'').substring(0,40)});
            });
            return JSON.stringify(r);
        })()""")
        for inp in json.loads(inp_json3):
            if inp['id'] or inp['name'] or inp['type'] in ('text','date'):
                print(f"  {inp}")
    except Exception as e:
        print(f"  click 工作日志 failed: {e}")

    b.close()
