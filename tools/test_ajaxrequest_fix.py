#!/usr/bin/env python3
"""Test: adding AJAXREQUEST field to HTTP-only saveLog POST"""
import os, json, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,10.111.36.3'
os.environ['no_proxy'] = 'localhost,127.0.0.1,10.111.36.3'

from bs4 import BeautifulSoup
from app import RDMClient, normalize_to_monday, encode_unplanned_info_single_day, S1,S2,S3,S4

import getpass
client = RDMClient()
_user = os.environ.get('RDM_USER') or input('RDM 用户名: ').strip()
_pass = os.environ.get('RDM_PASS') or getpass.getpass('RDM 密码: ').strip()
if not _user or not _pass:
    print('[X] 需要 RDM 账号（RDM_USER/RDM_PASS 环境变量 或手动输入）')
    sys.exit(1)
client.login(_user, _pass)

week_start = normalize_to_monday('2025-06-01')

# 1. GET page and extract container ID from saveLog onclick
print('[STEP 1] Extract A4J container ID...')
r = client._request('GET', f'/pages/myspace/log/workLogView.jsf?startDate={week_start}&isView=N')
soup = BeautifulSoup(r.text, 'html.parser')

ctx = client.get_week_existing(week_start)

# Find saveLog element and extract container ID
save_log_el = soup.find(id='operate:saveLog')
container_id = ''
if save_log_el and save_log_el.get('onclick'):
    onclick = save_log_el['onclick']
    m = re.search(r"A4J\.AJAX\.Submit\('([^']+)'", onclick)
    if m:
        container_id = m.group(1)
        print(f'  Container ID: {container_id}')
else:
    print('  Could not find saveLog element!')
    # Try regex from the whole page
    m = re.search(r"A4J\.AJAX\.Submit\('([^']+)','operate'", r.text)
    if m:
        container_id = m.group(1)
        print(f'  Found in raw HTML: {container_id}')

# 2. Try HTTP POST WITH AJAXREQUEST
print('\n[STEP 2] POST with AJAXREQUEST...')
tid = '2303bf8f-5937-49d7-9946-7dba5dfd95cf'
unplanned = encode_unplanned_info_single_day(tid, 6, 5, 5)
seven_blanks = S2.join([' '] * 7)

form = {
    'AJAXREQUEST': container_id,  # KEY FIX!
    'operate': 'operate',
    'operate:saveLog': 'operate:saveLog',
    'javax.faces.ViewState': ctx['view_state'],
    'startDate': week_start,
    'isView': 'N',
    'isOwner': 'Y',
    'unplannedInfo': unplanned,
    'workRemark': seven_blanks,
    'issueRemark': seven_blanks,
}

headers = {
    'Faces-Request': 'partial/ajax',
    'X-Requested-With': 'XMLHttpRequest',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
}

r = client._request('POST', '/pages/myspace/log/workLogView.jsf', data=form, headers=headers)
print(f'  HTTP {r.status_code}  len={len(r.text)}')
print(f'  Content-Type: {r.headers.get("Content-Type", "")}')

text = r.text
is_xml = text.strip()[:20].startswith('<?xml')
print(f'  Is XML response: {is_xml}')

if is_xml:
    print('  [OK] Got XML partial response! AJAXREQUEST is the key!')
    msg_match = re.search(r'operate:operateMessage.*?value="([^"]*)"', text)
    if msg_match:
        msg_val = msg_match.group(1)
        print(f'  operateMessage: {repr(msg_val)}')
        if msg_val:
            print(f'  [WARN] RDM error: {msg_val}')
        else:
            print(f'  [OK] No RDM error message')

    # Show full relevant part of response
    unplanned_match = re.search(r'name="unplannedInfo"[^>]*', text)
    if unplanned_match:
        print(f'  unplannedInfo in resp: {unplanned_match.group(0)[:100]}')
else:
    print('  [X] Still HTML - need more investigation')
    print(f'  First 200: {text[:200]}')

# 3. Verify
print('\n[STEP 3] Verify data persistence...')
ctx2 = client.get_week_existing(week_start)
print(f'  entries count: {len(ctx2["entries"])}')
for e in ctx2['entries']:
    print(f'  task_id={e["task_id"]} hours={e["hours"]} rates={e["completion_rates"]}')

if len(ctx2['entries']) == 0:
    data_obj = json.loads(ctx2['data_json']) if ctx2['data_json'] else {}
    unbody = data_obj.get('unBody', [])
    print(f'  unBody from raw data: {json.dumps(unbody, ensure_ascii=False)[:300]}')
