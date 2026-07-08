#!/usr/bin/env python3
import argparse
import getpass
import sys
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import base64

base_url = "http://10.111.36.3:2029"
session = requests.Session()


# 登录函数
def encrypt(text):
    cipher = AES.new(b"abcdefgabcdefg12", AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
    return base64.b64encode(encrypted).decode('utf-8')


# 从命令行参数或交互输入读取账号密码
def get_credentials():
    parser = argparse.ArgumentParser(description="RDM 页面探测工具")
    parser.add_argument("--user", "-u", help="RDM 用户名")
    parser.add_argument("--pass", "-p", dest="password", help="RDM 密码")
    args = parser.parse_args()

    username = args.user or input("用户名: ").strip()
    password = args.password or getpass.getpass("密码: ").strip()

    if not username or not password:
        print("[X] 用户名和密码不能为空")
        sys.exit(1)

    return username, password


# 登录
username, password = get_credentials()
session.get(f"{base_url}/index.jsp")
encrypted_username = encrypt(base64.b64encode(username.encode('utf-8')).decode('utf-8'))
encrypted_password = encrypt(base64.b64encode(password.encode('utf-8')).decode('utf-8'))

session.post(f"{base_url}/j_security_check", data={
    "j_username": encrypted_username,
    "j_password": encrypted_password,
    "isExpires": "1",
    "BROWSER_VERSION": "1",
    "REMOTE_LANGUAGE": "zh-cn"
}, allow_redirects=True)

# 测试我的任务页面
print("访问: /pages/task/list/myTask.jsf")
resp = session.get(f"{base_url}/pages/task/list/myTask.jsf")
print(f"状态码: {resp.status_code}, 长度: {len(resp.text)}")
with open('myTask.html', 'w', encoding='utf-8') as f:
    f.write(resp.text)

# 测试工作日志页面
print("\n访问: /pages/myspace/log/workLogList.jsf")
resp = session.get(f"{base_url}/pages/myspace/log/workLogList.jsf")
print(f"状态码: {resp.status_code}, 长度: {len(resp.text)}")
with open('workLogList.html', 'w', encoding='utf-8') as f:
    f.write(resp.text)

# --- A4J 诊断 ---
print("\n=== A4J 诊断 ===")
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
session.headers.update({'User-Agent': UA})

MYTASK = f"{base_url}/pages/task/list/myTask.jsf"

# 重新 GET（带新 UA）
r = session.get(MYTASK, timeout=15)
soup = BeautifulSoup(r.text, 'html.parser')

# 提取全部 hidden
form = {}
for inp in soup.find_all('input', type='hidden'):
    form[inp['name']] = inp.get('value', '')

print(f"hidden 字段: {len(form)} 个")
print(f"  refreshType={form.get('refreshType')!r}")
print(f"  page={form.get('page')!r}")
print(f"  cate={form.get('cate')!r}")

# 拼 A4J 请求
form['operate:refreshBody'] = 'operate:refreshBody'
form['cate'] = '0'
form['refreshType'] = '0'
form['page'] = '1'
form['isInit'] = 'Y'
form.pop('operate:_path', None)
form.pop('operate:_fileName', None)
form.pop('operate:_fileContentType', None)

headers = {
    'Faces-Request': 'partial/ajax',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': MYTASK,
    'Accept': '*/*',
}

r0 = session.post(MYTASK, data=form, headers=headers, timeout=15)
print(f"\nA4J cate=0: HTTP {r0.status_code}  len={len(r0.text)}")
print(f"  前60字节: {r0.text[:60]!r}")
print(f"  body-row 关键词: {'body-row' in r0.text} (出现 {r0.text.count('body-row')} 次)")

s0 = BeautifulSoup(r0.text, 'html.parser')
trs0 = s0.find_all('tr', class_='body-row')
print(f"  解析到 body-row <tr>: {len(trs0)} 行")
for tr in trs0[:5]:
    st = tr.get('status', '?')
    tds = tr.find_all('td', recursive=False)
    print(f"    status={st}  id={tr.get('id','?')[:36]}  td数={len(tds)}")

# cate=22
new_vs = s0.find('input', attrs={'name': 'javax.faces.ViewState'})
if new_vs and new_vs.get('value'):
    form['javax.faces.ViewState'] = new_vs['value']
    print(f"  新 ViewState: 已更新")
form['cate'] = '22'

r22 = session.post(MYTASK, data=form, headers=headers, timeout=15)
print(f"\nA4J cate=22: HTTP {r22.status_code}  len={len(r22.text)}")
print(f"  body-row: {'body-row' in r22.text} (出现 {r22.text.count('body-row')} 次)")
s22 = BeautifulSoup(r22.text, 'html.parser')
trs22 = s22.find_all('tr', class_='body-row')
print(f"  解析到 body-row <tr>: {len(trs22)} 行")

print(f"\n=== 结果: cate=0 有 {len(trs0)} 行, cate=22 有 {len(trs22)} 行 ===")

# 保存 A4J 响应
with open('tools/myTask_a4j_cate0.txt', 'w', encoding='utf-8') as f:
    f.write(r0.text)
with open('tools/myTask_a4j_cate22.txt', 'w', encoding='utf-8') as f:
    f.write(r22.text)
print("A4J 响应已保存到 tools/myTask_a4j_cate{0,22}.txt")
