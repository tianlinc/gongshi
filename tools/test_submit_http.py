#!/usr/bin/env python3
"""纯 Python HTTP 测试 saveLog 提交——验证 A4J saveLog 是否接受非浏览器 POST"""
import time, base64, json, re
from pathlib import Path
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from bs4 import BeautifulSoup

BASE = "http://10.111.36.3:2029"
TASK_ID = "2303bf8f-5937-49d7-9946-7dba5dfd95cf"
WEEK_START = "2026-06-01"
HOUR, RATE = 8, 2
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def enc(t):
    c = AES.new(b"abcdefgabcdefg12", AES.MODE_ECB)
    return base64.b64encode(c.encrypt(pad(t.encode(), AES.block_size))).decode()

creds = Path(__file__).parent / ".rdm_creds"
lines = creds.read_text().strip().splitlines()
u, p = lines[0].strip(), lines[1].strip()

ses = requests.Session()
ses.headers["User-Agent"] = UA

# Login
ses.get(f"{BASE}/index.jsp")
eu = enc(base64.b64encode(u.encode()).decode())
ep = enc(base64.b64encode(p.encode()).decode())
r = ses.post(f"{BASE}/j_security_check", data={
    "j_username": eu, "j_password": ep, "isExpires": "1",
    "sessionIndex": "", "BROWSER_VERSION": "1", "REMOTE_LANGUAGE": "zh-cn",
}, allow_redirects=True)
print(f"[OK] login: JSESSIONID={ses.cookies.get('JSESSIONID','?')[:20]}")

# Get workLogView page
r = ses.get(f"{BASE}/pages/myspace/log/workLogView.jsf")
soup = BeautifulSoup(r.text, "html.parser")
vs = soup.find("input", {"name": "javax.faces.ViewState"})
vs_val = vs["value"] if vs else ""
print(f"[OK] ViewState len={len(vs_val)}")

# Get report_action_date input
date_input = soup.find("input", {"id": "report_action_date"})
print(f"  report_action_date: {date_input.get('value','?') if date_input else 'NOT FOUND'}")

# GET with startDate param
r = ses.get(f"{BASE}/pages/myspace/log/workLogView.jsf?startDate={WEEK_START}&isView=N")
soup = BeautifulSoup(r.text, "html.parser")
vs2 = soup.find("input", {"name": "javax.faces.ViewState"})
vs_val2 = vs2["value"] if vs2 else vs_val
print(f"[OK] ViewState(after date) len={len(vs_val2)}")

# Extract data JSON
data_inp = soup.find("input", {"id": "data"})
data_json = data_inp["value"] if data_inp and data_inp.get("value") else "{}"
data_obj = json.loads(data_json) if data_json else {}
print(f"  data keys: {list(data_obj.keys())}")

# Get loginUser
login_user = ""
lu = soup.find("input", {"id": "loginUser"})
if lu: login_user = lu.get("value", "")
print(f"  loginUser: {login_user[:20] if login_user else 'empty'}")

# Get reportId
report_id = ""
rid = soup.find("input", {"id": "reportId"})
if rid: report_id = rid.get("value", "")
print(f"  reportId: {report_id[:20] if report_id else 'empty'}")

# Build _unplannedInfo (single task, single day, day_index=0)
S1, S2, S3, S4 = "#-@%!-@#", "#-%@-#@", "#-%#!#-@-#@", "#-%#!A-#-@-#@"
rate_str = str(RATE) if RATE is not None else " "
effort_str = str(HOUR)
unplan = (f"{TASK_ID}{S1}0{S1}0"
          f"{S2}_rate{S4}{rate_str}"
          f"{S2}_effort{S4}{effort_str}"
          f"{S2}_remark{S4} "
          f"{S2}_issue{S4} "
          f"{S3}")
print(f"\n  _unplannedInfo: {unplan}")

# POST saveLog
seven = S2.join([" "] * 7)
form = {
    "operate": "operate",
    "operate:saveLog": "operate:saveLog",
    "javax.faces.ViewState": vs_val2,
    "startDate": WEEK_START,
    "isView": "N",
    "userId": "",
    "isOwner": "Y",
    "objectId": report_id,
    "summary": "",
    "workRemark": seven,
    "issueRemark": seven,
    "rightUserId": "",
    "unplannedInfo": unplan,
    "loginUser": login_user,
    "data": data_json,
}
headers = {
    "Faces-Request": "partial/ajax",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

print("\nPOST saveLog...")
r = ses.post(f"{BASE}/pages/myspace/log/workLogView.jsf", data=form, headers=headers)
print(f"HTTP {r.status_code}  len={len(r.text)}")
print(f"  starts: {r.text[:100]!r}")

# Check response
if r.status_code >= 500:
    print("[X] RDM server error")
elif "viewExpired" in (r.text or ""):
    print("[X] ViewState expired")
elif "loginForm" in (r.text or "") and len(r.text) < 15000:
    print("[X] Session lost (login form)")
elif "<?xml" in (r.text or "")[:50]:
    print("[OK] A4J XML response (successful A4J request!)")
    # Check for error message
    msg_el = BeautifulSoup(r.text, "html.parser").find(id="operate:operateMessage")
    print(f"  operateMessage: {msg_el.get('value','')[:200] if msg_el else 'not found'}")
elif "DOCTYPE" in (r.text or "")[:50]:
    print("[X] Got full HTML page — A4J NOT triggered (same old problem)")
else:
    print(f"  unknown response format")

print("\n[OK] Check RDM to see if hours were submitted for 6/1")
