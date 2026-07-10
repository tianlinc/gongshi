# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Flask web app that wraps the company RDM platform (`http://10.111.36.3:2029`) to make weekly timesheet entry faster than the native UI.

**实现状态（2026-06-25 最终）：**
- ✅ 登录流程 — 双重编码 AES-ECB，`RDMClient.login()` (L166-209)
- ✅ 任务获取 — Playwright headless 浏览器抓取（`threading.local()` 单例），`RDMClient.get_my_tasks()` (L218-326)
- ✅ 工时提交 — `entity.jsf` → `taskForm:save` 简单 form 提交，`RDMClient.submit_day()` (L484-621)
- ✅ 已填工时回显 — 解析 unBody（仍走 `workLogView.jsf`），`RDMClient.get_week_existing()` (L371-482)
- ✅ 端到端闭环 — 用户真实验证通过（InManage监控组 6月3号提交成功）
- ✅ License 激活与账号绑定 — 完整链路：SN 生成 → License 签发 → 激活校验 → 运行时 SN 比对（INSPUR-48 修复），详见下方 License 章节
- ✅ 安装包瘦身 — 排除 cefpython3 (108MB)、Pythonwin (6.5MB)、prebuilt Chromium (656MB)，安装包体积大幅缩减
- ⚠️ `_unplannedInfo` 编码已废弃（保留代码供参考，L44-86）

## Run / install

```bash
pip install flask flask-cors requests pycryptodome beautifulsoup4 playwright pywebview
playwright install chromium
python app.py           # Web 版本：命令行启动
# → http://localhost:5000
```

桌面版打包：`cd service_installer && build.bat`（详见下方"Windows 桌面打包"章节）。

There is no test suite, linter config, or build step. The Flask app runs with `debug=True` so edits hot-reload.

## Architecture

**Single-file backend** (`app.py`) — one `RDMClient` class wrapping the RDM HTTP session, plus thin Flask routes. Two-page frontend in `templates/` (Bootstrap 5 + vanilla JS, no build).

The piece that's easy to get wrong: **RDM login requires double-encoding credentials** — base64 first, then AES-ECB with the hardcoded key `abcdefgabcdefg12` (lifted from RDM's own `/scripts/index.js`). Both `j_username` and `j_password` go through this. See `RDMClient.encrypt()` and `RDMClient.login()`.

**Session model**: Flask `session` only stores `username` + `logged_in`. The actual authenticated `requests.Session` lives in the module-level `clients` dict keyed by username. This means restarting Flask drops all RDM sessions even though browser cookies persist — users will silently get "未登录" on `/api/*` routes. If you change session handling, this is the trap.

## License 激活与账号绑定

**INSPUR-48 完成（2026-06-25）：** License 模块实现完整的激活→校验→账号绑定闭环，基于 HMAC-SHA256 签名 + Base64(JSON) 格式，由老王确认算法方案。

### 模块文件

| 文件 | 作用 |
|------|------|
| `license_utils.py` | License 核心逻辑（SN 生成、License 签发/验证、状态读写、激活校验） |
| `app.py` L1381-1443, L1840-1917 | Web 层：统一拦截器 + 3 个 License API + 页面路由 |
| `license_status.json` | 本地激活状态持久化（字典结构，按 SN 索引，支持多用户） |
| `templates/activate.html` | 激活页面（展示 SN、输入 License） |
| `static/js/app.js` L116-118 | 前端拦截：API 返回 `need_activate` 时跳转 `/activate` |
| `tools/license_generator.py` | 管理员工具：根据 SN 签发 License（独立运行，复用 `license_utils`） |

### 完整逻辑链路

#### 1. SN 生成 `license_utils.py:48-57`

```python
generate_sn(username) → base64(username)
```

- 纯基于用户名，**无硬件绑定**（Web 端无法可靠获取硬件序列号，老王确认）
- SN 天然区分不同用户：`base64("tianlin")` ≠ `base64("zhangsan")`
- 用户将 SN 码发给管理员以换取 License

#### 2. License 签发 `license_utils.py:64-103` + `tools/license_generator.py`

管理员运行 `tools/license_generator.py`，输入客户 SN + 时长（1年/永久）：

```python
generate_license(sn, duration_type) → "Base64(JSON).签名hex前16位"
```

- Payload: `{"sn": "<sn>", "type": "<1年|永久>", "exp": "<ISO日期>"|null}`
- 签名: `HMAC-SHA256(payload_b64, secret_key)[:16]` hex
- 密钥来源：`RDM_SECRET_KEY` 环境变量（未设置则用默认开发密钥 `gongshi_license_default_key_2026`）
- **⚠️ 更换密钥会导致所有已签发 License 失效**

#### 3. License 验证 `license_utils.py:110-164`

```python
verify_license(license_str) → (valid: bool, payload: dict, error: str)
```

三步校验：
1. HMAC-SHA256 签名校验（防篡改，`hmac.compare_digest` 防时序攻击）
2. Base64 JSON payload 解析
3. 过期时间检查（`exp` 字段非 null 时比对当前日期）

#### 4. 激活流程 `app.py:1872-1917` + `license_utils.py:264-284`

```
POST /api/license/activate {license: "..."}
    ↓
① verify_license(license_str)     — 验证签名 + 过期
② current_sn ≠ license_sn?        — SN 匹配校验（防跨用户使用）
③ activate(sn, license_str, payload) → 写入 license_status.json
```

- 激活接口内的 SN 匹配校验**从一开始就是正确的** ✅
- 写入内容：`{activated: true, sn, type, exp, activated_at, license}`

#### 5. 运行时校验与账号绑定 `license_utils.py:221-261` + `app.py:1381-1413`

**每次 API 请求的统一拦截链**（`_intercept_unauth_api()`, L1381-1413）：

```
/api/* 请求
    ↓
登录豁免：/api/login, /api/logout → 放行
    ↓
登录检查：get_client() is None → 200 {"未登录"}
    ↓
激活豁免：/api/license/* → 放行（激活流程本身需要访问）
    ↓
激活检查：check_activated(username) → 403 {"未激活", need_activate: true}
```

**`check_activated(username)` 逻辑** (L221-261)：

1. 读 `license_status.json` → `activated` 为 false 则拒绝
2. **★ 账号绑定校验**（INSPUR-48 新增）：传入 `username` 时，计算 `current_sn = base64(username)` 并与存储的 `sn` 比对。不匹配 → 视为当前用户未激活
3. 过期检查：已过期 → 自动标记 `activated=False` 并写回

**4 处调用点全部传入当前用户名**（INSPUR-48 修复）：

| 位置 | 场景 | 行号 |
|------|------|------|
| `_intercept_unauth_api()` | 每次 `/api/*` 请求拦截 | L1405 |
| `index()` | 首页路由（登录态判断跳转目标） | L1420 |
| `dashboard()` | 主表页面壳 | L1440 |
| `api_license_info()` | License 信息查询 | L1858 |

#### 6. 前端拦截

**API 层** (`static/js/app.js:116-118`)：所有 `fetch()` 统一检查响应 `data.need_activate`，为 true 时跳转 `/activate`。

**页面路由层** (`app.py:1416-1443`)：
- `index()` → 已登录+未激活 → redirect `/activate`
- `dashboard()` → 未激活 → redirect `/activate`
- `activate_page()` → 未登录 → redirect `/`

三层拦截确保未激活用户无法通过直接输入 URL 绕过。

### 切换账号场景行为（INSPUR-48 修复后）

```
用户 A（tianlin）激活 →
  license_status.json: {sn: "dGlhbmxpbg==", activated: true}

用户 B（zhangsan）登录同一台机器 →
  发 API 请求 → check_activated("zhangsan")
    → current_sn = base64("zhangsan") ≠ stored_sn "dGlhbmxpbg=="
    → 返回 (False, status) → 403 → 前端跳转 /activate ✓

用户 B 必须获取自己的 SN，让管理员签发自己的 License 才能使用 ✓
```

### 状态存储

`license_status.json` 结构（INSPUR-57 升级为字典格式，路径见 `_get_status_file_path()`）：

```json
{
  "dGlhbmxpbg==": {
    "activated": true,
    "sn": "dGlhbmxpbg==",
    "type": "1年",
    "exp": "2027-06-25T00:00:00",
    "activated_at": "2026-06-25T15:02:26",
    "license": "eyJzbiI6..."
  },
  "emhhbmdzYW4=": {
    "activated": true,
    "sn": "emhhbmdzYW4=",
    "type": "永久",
    "exp": null,
    "activated_at": "2026-06-30T10:00:00",
    "license": "eyJzbiI6..."
  }
}
```

- 顶层 key 为 SN（`base64(username)`），天然区分不同用户
- 开发模式：与 `license_utils.py` 同目录
- 打包模式（`sys.frozen`）：`%APPDATA%/gongshi/license_status.json`
- **自动迁移**：`_read_all_status()` 检测旧格式（顶层含 `activated` 键）时自动包装为 `{sn: data}` 并写回
- **多用户支持**（INSPUR-57）：一台机器可保留多个账号的激活记录，各自独立，互不影响

### License API 清单

| 路由 | 方法 | 功能 | 行号 |
|------|------|------|------|
| `/api/license/sn` | GET | 返回当前用户 SN 码 | L1844-1852 |
| `/api/license/info` | GET | 返回激活信息（不含完整 License 字符串） | L1855-1869 |
| `/api/license/activate` | POST | 激活 License（需 `{"license": "..."}`） | L1872-1917 |

### 注意事项

- **Secret key 一致性**：签发工具和 Web 验证端必须使用相同的 `RDM_SECRET_KEY`。部署到生产环境前必须设置环境变量，否则使用默认开发密钥。
- **多用户各自激活**（INSPUR-57）：`license_status.json` 为字典结构 `{sn: {activated, ...}}`，不同用户互不影响。
- **无硬件绑定**：SN = base64(username)，如果用户知道别人的用户名就能算出别人的 SN。当前方案依赖 License 签名（HMAC-SHA256）防伪造，不依赖 SN 保密。
- **`/api/license/*` 路由绕过激活检查**：这是有意设计——用户未激活时必须能访问这些接口完成激活流程。

## 混合方案架构（2026-06-23 最终版）

**任务获取**：Playwright headless 浏览器 (`get_my_tasks()`, L218-326)
- 复用 HTTP session 的 cookie 注入 Playwright context
- goto `myTask.jsf` 一次，点击 "我负责"/"我参与" radio 按钮切换 scope
- 每次点击后等待 A4J 刷新（判断 `tr.body-row` 数量变化 或 networkidle 兜底）
- **日期过滤器**：radio 刷新后自动点击 `span.menu-more` → 选"所有"（v=5），确保未启动（NS）任务不被 RDM 的日期范围过滤器排除（NS 任务计划开始日期可能在将来，默认"周"过滤器会排除它们）
- 合并去重，过滤 status ∈ {RN, NR}（RN=进行中, NR=未启动。HAR 实证：RDM HTML `tr.body-row` 的 `status` 属性值为 NR 非 NS）
- 浏览器实例使用 `threading.local()` 线程安全单例（`_get_browser()`, L623-632），避免 Playwright 跨线程调用错误

**工时提交**：`entity.jsf` → `taskForm:save` 简单 form 提交 (`submit_day()`, L484-621)
- 提交前 GET `entity.jsf?taskId=...` 获取 ViewState + AJAX container ID（`get_entity_page()`, L328-369）
- POST 使用简单的 key=value 字段（`report_action_date`/`report_rate`/`report_in_work`/`taskForm:save`），无需 `_unplannedInfo` 编码
- ViewState 过期时自动重新登录 + 重试 1 次（L573-584）
- `app.debug=True` 时输出完整请求/响应日志（L521-561）
- **HAR 参照**：`tools/har/10.111.36.3.har` Entry #3 为真实验证过的提交流程

**已填工时回显**：`get_week_existing()` (L371-482) GET `workLogView.jsf`，解析 HTML 中 `#data` input（unBody JSON），填回 7 天数组。

**弃用模块**：`_unplannedInfo` 编码（L44-86）—分隔符常量 S1/S2/S3/S4 来自 `scripts/myspace/unplannedTask.js` 实证。entity.jsf 路径不需要编码，此代码保留供参考，稳定后可安全删除。

## Exploration tools (`tools/`)

### 脚本
- `tools/explore.py` — re-runs the full menu/page sweep against RDM, saves HTML samples. Run when the RDM UI changes or to rediscover endpoints.
- `tools/test_pages.py` — fetches a known page directly (login + GET).
- `tools/test_ajaxrequest_fix.py` — HTTP-only POST to entity.jsf (验证 AJAXREQUEST 必要性，**运行需设 RDM_USER/RDM_PASS 环境变量**)
- `tools/test_a4j_save.py` — Playwright A4J.AJAX.Submit 真实提交流程（**运行需设 RDM_USER/RDM_PASS 环境变量**）
- `tools/playwright_tasks.py` — Playwright 纯任务列表抓取
- `tools/playwright_submit_test.py` — Playwright 工时提交流程测试
- `tools/test_submit_http.py` — HTTP 直连 entity.jsf 提交测试
- `tools/find_date_input.py` / `tools/find_date_v2.py` — 日期输入字段定位脚本
- `tools/parse_har.py` / `tools/parse_har2.py` / `tools/parse_har3.py` — HAR 文件解析脚本

### 子目录
- `tools/har/` — F12 HAR 抓包文件。`10.111.36.3.har` Entry #3 为 entity.jsf → taskForm:save 真实验证参照
- `tools/html/` — RDM 页面 HTML/TXT 快照（`main_page.html` 是菜单；`myTask.html`/`workLogList.html` 是目标页面）
- `tools/screenshots/` — 诊断截图（`_diag_*.png`）
- `tools/captured/` — JS 逆向产物（RDM 页面 JavaScript 反混淆/提取）

**⚠️ 安全规则**：所有需要 RDM 凭证的脚本必须通过 `RDM_USER`/`RDM_PASS` 环境变量提供，禁止在代码中硬编码密码。禁止对 RDM 发起写操作（POST saveLog/entity.jsf）除非显式确认。

When asked to "find the API for X", default workflow: run `tools/test_pages.py` against the suspected page → save the HTML → grep for AJAX URLs (`A4J.AJAX.Submit`, `actionUrl`, DWR interfaces) → check `tools/har/10.111.36.3.har` for existing HAR captures → only escalate to live F12 capture if static analysis comes up empty.

## Windows 桌面打包 (`service_installer/`)

**INSPUR-36 完成：** PyInstaller + pywebview 方案，产出独立桌面 exe。INSPUR-79 精简后仅保留 service_installer 打包形式，
desktop 和 lightweight 打包形式已删除。

### 文件结构
```
├── _desktop_common.py  ★ 共享启动器模块（DesktopLauncher + CredentialManager）
service_installer/
├── service_launcher.py  ★ 启动器（薄层，调用 DesktopLauncher，port_auto=True）
├── service.spec         ★ PyInstaller spec（console=False, onedir）
├── build.bat             一键构建脚本（含 Inno Setup 安装包编译）
├── requirements.txt      依赖清单
├── README.md             打包/分发说明
├── installer/
│   ├── setup.iss        Inno Setup 安装脚本（中文 UI）
│   └── iei_timer.ico    应用图标
├── dist/                 构建产物
│   └── IEI Timer Faster/
│       └── IEI Timer Faster.exe
```

### 技术选型
- **PyInstaller**（非 Nuitka）：Playwright 兼容性成熟
- **pywebview + Edge WebView2**：独立桌面窗口（非系统浏览器），Win10/11 自带引擎
- **Chromium 由 Playwright 自行管理**：运行时通过 `playwright install chromium` 安装，网络环境受限时需提前准备
- **Inno Setup**：最终产出安装包 `.exe`，带中文 UI 和桌面快捷方式
- **`console=False`**：GUI 模式，不弹 cmd 黑窗口
- **`cefpython3` 已排除**：仅使用 Edge WebView2，CEF 后端 108MB 不再打包

### `service_launcher.py` 关键设计（不修改 `app.py` 和 `templates/`）

共享逻辑统一在 `_desktop_common.py` 的 `DesktopLauncher` 类中：

| 功能 | 实现方式 |
|------|---------|
| 导入 Flask | `sys.path.insert(0, bundle_dir)` → `from app import app` |
| Flask 启动 | daemon 线程（GUI 模式），`debug=False, host=127.0.0.1` |
| 桌面窗口 | `webview.create_window('IEI Timer Faster', 'http://127.0.0.1:5000')` |
| 免登录 API | `before_request_funcs[None].insert(0, ...)` 短路 `_intercept_unauth_api` |
| 凭证记忆 | `POST/GET/DELETE /api/saved-credentials` → AES-ECB 加密存 `credentials.dat` |
| 登录页自动回填 | `after_request` 注入 JS 脚本（fetch API + form fill） |
| CDN 本地化 | Bootstrap/Icons 下载到 `static/lib/`，`after_request` 改写 URL |
| Playwright Chromium | 由 Playwright 库自行下载管理，不在安装包中预打包 |
| 初始化加载页 | `/init` 路由（纯内联 HTML+CSS+JS），预打包就绪时跳过；仅下载失败时回退展示 |
| 同步按钮常开 | 注入 JS `setInterval` 每 300ms 强制 `syncBtn.disabled = false` |
| 日志 | `console=False` 时 stdout/stderr → `%APPDATA%/gongshi/run.log` |
| WebView2 持久化 | `WEBVIEW2_USER_DATA_FOLDER` → `%APPDATA%/gongshi/webview-data/` |
| 端口策略 | `port_auto=True`：5000 被占用则自动递增到 5001、5002 |

### 用户数据目录
```
%APPDATA%/gongshi/
├── run.log                程序日志
├── credentials.dat        AES 加密凭证
├── webview-data/          WebView2 cookie/缓存
├── ms-playwright/         Playwright Chromium（运行时自动下载）
└── cache/
    ├── holidays_2026.json  节假日（自动同步，TTL 24h）
    └── *_tasks.json        任务缓存（TTL 4h，不预置）
```

### 构建命令
```bash
cd service_installer
pip install pyinstaller pywebview
# 完整构建（PyInstaller + Inno Setup 安装包）
build.bat
```

### 注意事项
- **共享模块**（INSPUR-77）：`_desktop_common.py` 位于项目根目录，包含 `DesktopLauncher` 类和 `CredentialManager`。`service.spec` 的 hiddenimports 需包含 `'_desktop_common'`。
- **不改 Web 源码**：所有桌面逻辑通过 `service_launcher.py` 注入（路由、`before_request`/`after_request` 钩子、JS 注入）
- **`_intercept_unauth_api` 鉴权**：新 API 必须通过 `before_request_funcs` 短路，不能 monkey-patch `get_client()`（PyInstaller 下不生效）
- **首次启动**：Playwright 会自动下载 Chromium（需网络连接），后续启动复用已安装的浏览器
- **产品名称**：exe 文件名为 `IEI Timer Faster.exe`，版本 V1.0.0

## `archive/`

Old v1 of the same project — earlier `app.py`, CLI tool (`rdm_timesheet.py`), old templates and docs. Reference only; **do not edit**. If you find yourself wanting to revive something from here, copy it into the live tree first.

## Conventions specific to this codebase

- **Windows console can't print Unicode arrows.** Use `[OK]` / `[X]` instead of `✓` / `✗` in any script that prints to stdout — the system encoding is GBK and unicode arrows crash with `UnicodeEncodeError`. `tools/explore.py` was rewritten to follow this; keep it that way.
- **All user-facing strings are Chinese** (UI labels, error messages, doc filenames like `使用说明.md`). Match this when adding routes or messages.
- **The RDM base URL is hardcoded** to `http://10.111.36.3:2029` in `RDMClient.__init__`. Not configurable yet — change it there if needed.
- **`docs/` has two Chinese guides** (`使用说明.md` technical, `完整说明-用户版.md` end-user). The README is the canonical English-ish overview; the two docs are for the user, not for navigating the code.
