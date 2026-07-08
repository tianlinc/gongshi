#!/usr/bin/env python3
"""直接调用 A4J.AJAX.Submit 测试 saveLog，捕获完整请求/响应"""
import os, json, time, base64, sys
os.environ['NO_PROXY'] = 'localhost,127.0.0.1,10.111.36.3'
os.environ['no_proxy'] = 'localhost,127.0.0.1,10.111.36.3'

from playwright.sync_api import sync_playwright
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from urllib.parse import parse_qs

BASE = 'http://10.111.36.3:2029'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

def encrypt(t):
    c = AES.new(b'abcdefgabcdefg12', AES.MODE_ECB)
    return base64.b64encode(c.encrypt(pad(t.encode(), AES.block_size))).decode()

# Login via HTTP
print('[1] Login...')
s = requests.Session()
s.headers['User-Agent'] = UA
s.get(f'{BASE}/index.jsp', timeout=15)
	import getpass
	_user = os.environ.get('RDM_USER') or input('RDM 用户名: ').strip()
	_pass = os.environ.get('RDM_PASS') or getpass.getpass('RDM 密码: ').strip()
	if not _user or not _pass:
	    print('[X] 需要 RDM 账号（RDM_USER/RDM_PASS 环境变量 或手动输入）')
	    sys.exit(1)
	eu = encrypt(base64.b64encode(_user.encode()).decode())
	ep = encrypt(base64.b64encode(_pass.encode()).decode())
r = s.post(f'{BASE}/j_security_check', data={
    'j_username': eu, 'j_password': ep, 'isExpires': '1',
    'sessionIndex': '', 'BROWSER_VERSION': '1', 'REMOTE_LANGUAGE': 'zh-cn',
}, allow_redirects=True, timeout=15)
cookies = s.cookies.get_dict()
pw_cookies = [{'name': k, 'value': v, 'domain': '10.111.36.3', 'path': '/'} for k, v in cookies.items()]
print('  OK')

print('[2] Playwright: fill form + A4J.AJAX.Submit...')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(user_agent=UA)
    context.add_cookies(pw_cookies)
    page = context.new_page()

    captured_post = []
    captured_resp = []

    def on_request(req):
        if req.method == 'POST' and 'workLogView' in req.url:
            captured_post.append({
                'headers': {k: v for k,v in dict(req.headers).items() if 'cookie' not in k.lower()},
                'postData': req.post_data,
            })

    def on_response(resp):
        if resp.request.method == 'POST' and 'workLogView' in resp.url:
            try:
                body = resp.body()
            except:
                body = b'<error>'
            captured_resp.append({
                'status': resp.status,
                'headers': {k: v for k,v in dict(resp.headers).items()},
                'body': body,
            })

    page.on('request', on_request)
    page.on('response', on_response)

    # Navigate
    page.goto(f'{BASE}/pages/myspace/log/workLogView.jsf?startDate=2025-05-26&isView=N', timeout=20000)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    print('  Page loaded')

    # Fill form fields
    TASK_ID = '2303bf8f-5937-49d7-9946-7dba5dfd95cf'
    S1 = '#-@%!-@#'
    S2 = '#-%@-#@'
    S3 = '#-%#!#-@-#@'
    S4 = '#-%#!A-#-@-#@'
    unplanned = f'{TASK_ID}{S1}6{S1}6{S2}_rate{S4}5{S2}_effort{S4}5{S2}_remark{S4} {S2}_issue{S4} {S3}'
    seven_blanks = S2.join([' '] * 7)

    login_user = page.evaluate("document.getElementById('loginUser') ? document.getElementById('loginUser').value : ''")
    data_json = page.evaluate("document.getElementById('data') ? document.getElementById('data').value : '{}'")

    print(f'  Setting form fields...')
    page.evaluate(f'''
        (function() {{
            function setVal(id, val) {{
                var el = document.getElementById(id);
                if (el) el.value = val;
            }}
            setVal('_startDate', '2025-05-26');
            setVal('_summary', '');
            setVal('_workRemark', '{seven_blanks}');
            setVal('_issueRemark', '{seven_blanks}');
            setVal('_rightUserId', '');
            setVal('_unplannedInfo', '{unplanned}');
        }})();
    ''')

    # Verify
    form_state = page.evaluate('''() => {
        var f = document.getElementById('operate');
        var result = {};
        var inputs = f.querySelectorAll('input[name]');
        inputs.forEach(function(inp) {
            result[inp.name] = inp.value ? inp.value.substring(0, 120) : '(empty)';
        });
        return JSON.stringify(result, null, 2);
    }''')
    print(f'  Form state: {form_state}')

    # Call A4J.AJAX.Submit
    print('\n  Calling A4J.AJAX.Submit...')
    result = page.evaluate('''() => {
        return new Promise(function(resolve) {
            var fakeEvent = {
                type: 'click',
                target: {id: 'operate:saveLog'},
                preventDefault: function() {},
                stopPropagation: function() {}
            };
            A4J.AJAX.Submit(
                'j_id_jsp_358727265_0',
                'operate',
                fakeEvent,
                {
                    'oncomplete': function(request, event, data) {
                        var rt = request.responseText || '';
                        resolve({
                            status: 'complete',
                            responseLength: rt.length,
                            responsePreview: rt.substring(0, 500),
                            isXml: rt.trim().startsWith('<?xml')
                        });
                    },
                    'parameters': {'operate:saveLog': 'operate:saveLog'},
                    'actionUrl': '/pages/myspace/log/workLogView.jsf'
                }
            );
            setTimeout(function() {
                resolve({status: 'timeout', note: 'A4J oncomplete not called within 15s'});
            }, 15000);
        });
    }''')
    print(f'  A4J result: {json.dumps(result, ensure_ascii=False, indent=2)}')

    page.wait_for_timeout(2000)

    print(f'\n  Network: {len(captured_post)} POST(s), {len(captured_resp)} response(s)')

    for i, req in enumerate(captured_post):
        print(f'\n  === POST Request #{i} ===')
        for k, v in sorted(req['headers'].items()):
            print(f'    {k}: {v}')

        pd = req['postData'] if isinstance(req['postData'], str) else req['postData'].decode('utf-8', errors='replace')
        params = parse_qs(pd)
        print(f'  Form fields ({len(params)}):')
        for k, v in sorted(params.items()):
            val = str(v[0])
            if k == 'javax.faces.ViewState':
                print(f'    {k} = <{len(val)} chars...{val[-20:]}>')
            elif k == 'unplannedInfo':
                print(f'    {k} = {val}')
            elif k == 'data':
                print(f'    {k} = <{len(val)} chars json>')
            elif len(val) > 80:
                print(f'    {k} = {val[:60]}...')
            else:
                print(f'    {k} = {val}')

    for i, resp in enumerate(captured_resp):
        print(f'\n  === Response #{i} ===')
        print(f'  Status: {resp["status"]}')
        ct = resp["headers"].get("content-type", "")
        print(f'  Content-Type: {ct}')
        body = resp['body'] if isinstance(resp['body'], str) else resp['body'].decode('utf-8', errors='replace')
        is_xml = body.strip()[:20].startswith('<?xml')
        print(f'  Type: {"XML PARTIAL!" if is_xml else "HTML/Other"}')
        if is_xml:
            print(f'\n  FULL XML RESPONSE:')
            print(body[:2000])
        else:
            print(f'  Body first 500: {body[:500]}')
            print(f'  Body last 500: {body[-500:]}')

    browser.close()
print('\n[DONE] Check RDM to verify if data was saved')
