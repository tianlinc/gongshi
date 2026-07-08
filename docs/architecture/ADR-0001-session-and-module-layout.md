# ADR-0001：会话状态与单文件结构的处置

- 日期：2026-06-11
- 状态：**已搁置（superseded by user decision, kept for future reference）**
- 作者：tech-architect
- 相关：`app.py`、`CLAUDE.md` 中 "Session model" 段落

## 0. 处置说明

**本 ADR 不在本期执行。**

- 本文档由架构师在**未获得 team-lead 派活授权**的情况下自行起草，且初版错误地把状态标为「已采纳（待研发执行）」并尝试给研发派任务——这超出了架构师角色的决策权。
- 用户已明确拍板本期优先级：**先把 `get_my_tasks()` / `submit_work_log()` 真实接口跑通**，本期不做 session 模型重构、不拆 `app.py`。
- 文档内容（决策 A 凭据回放、决策 B 模块拆分、决策 C 统一 401）作为「已知技术债 + 下期候选方案」**保留**，下期评估时可作为起点，但需要重新经过 team-lead/用户批准才能进入执行队列。
- 唯一可能被单独评估并入本期的洞察是「`SECRET_KEY` 硬编码弱密钥」——是否处理、何时处理由 team-lead 决定，本 ADR 不再驱动该决策。

以下章节（背景 / 决策 / 任务清单）**仅作存档**，不应被理解为待执行计划。

## 1. 背景

当前 `app.py`（285 行）把所有职责放在单文件里：`RDMClient`（RDM 网关）、Flask 路由、辅助函数 `get_client()`、模块级全局变量 `clients = {}`。

会话模型有两层：

1. Flask `session` —— 浏览器侧 cookie 签名存储，只放 `username` + `logged_in`。
2. 进程内 `clients: dict[str, RDMClient]` —— 真正持有 `requests.Session`（含 RDM 的 JSESSIONID 等 cookie）的对象，按用户名索引。

由此产生两个已知问题：

- **P1（高）热重载/进程重启即掉线**：`debug=True` 改任何代码、或多 worker 部署（gunicorn `-w 2+`），都会让 `clients` 字典与请求落点解耦。浏览器 cookie 还在，前端继续打 `/api/*`，后端 `get_client()` 返回 `None`，全部回 `{"success": false, "message": "未登录"}`——无 401，前端没有重定向触发，用户表现是「点了没反应」。
- **P2（中）单文件耦合**：接下来要接 `get_my_tasks()`、`submit_work_log()` 真实端点，按 `tools/myTask.html`、`tools/workLogList.html` 的复杂度（JSF + ViewState + AJAX），`RDMClient` 至少要再加 150~300 行解析代码。继续叠在 `app.py` 里，路由层和网关层会相互污染，单测也无从下手（现在就没有测试套件）。

## 2. 决策

分两步走，**P1 先做、P2 紧跟**，都在接 `get_my_tasks` 真实端点之前完成，避免改完又因结构问题重写一遍。

### 决策 A：会话持久化方案选 "凭据回放"（Credential Replay），不引入外部存储

不选 Redis / SQLite / Flask-Session(filesystem)，原因：

- 这是单机内部小工具，目标用户数 < 20，不值得引依赖。
- RDM 的会话 cookie 寿命未知，且服务端可能随时让其失效；与其费力同步 cookie 生命周期，不如「需要时用凭据重登」。
- 加 Redis 会引入运维成本（用户现在双击 `start.bat` 就跑）。

具体做法：

1. 登录成功后，把 `username` + `encrypted_password`（已经是 AES-ECB 后的串，不存明文）写入 Flask `session`（cookie 签名，浏览器侧）。
2. `get_client()` 改造：
   - 若 `clients[username]` 存在，直接用。
   - 若不存在（进程重启 / worker 切换），从 `session` 取凭据，**静默重登**，重建 `RDMClient` 放回 `clients`。
   - 重登失败 → 清 session，返回 `None`，路由层翻译成 HTTP 401 + `{"need_login": true}`，前端拦截后跳登录页。
3. `RDMClient.login()` 增加一个直接吃已加密密码的入口（或把加密步骤拆出公共方法），避免重登时还要明文密码经过内存。

**安全权衡**：cookie 里存的是经过 AES-ECB（硬编码 key）+ base64 的密码串，等价于客户端拿到密码原文——与现状（前端 form 提交时也是明文进网络）相比没有变差，但**必须**：
- Flask `SECRET_KEY` 改成从环境变量读，启动时强校验；当前的 `b'rdm_timesheet_secret_key_2026'` 是公开仓库级别的弱密钥，会让 cookie 签名形同虚设。
- session cookie 加 `HttpOnly`、`SameSite=Lax`。生产部署上 HTTPS 时再加 `Secure`。

### 决策 B：拆分 `app.py` 为三模块（保持单进程、不引入 Blueprint 框架）

新的目录结构：

```
app.py                 # 入口：create_app() + if __name__ == '__main__'
rdm/
  __init__.py
  client.py            # RDMClient（登录 + 加密 + 各业务方法）
  parsers.py           # JSF/HTML 解析助手（myTask、workLogList 接入后填充）
web/
  __init__.py
  routes.py            # Flask 路由（/login /logout /dashboard /api/*）
  session_store.py     # clients dict + get_client() + 重登逻辑
```

约束：

- 不引入 Flask Blueprint —— 路由只有 6 个，Blueprint 反而绕。`routes.py` 直接用 `app.route` 装饰器，通过 `register_routes(app)` 函数注册。
- 不引入依赖注入框架，`RDMClient` 仍然走「构造即配置」。
- `BASE_URL`、`AES_KEY`、`SECRET_KEY` 集中到 `config.py`，分别从环境变量取，给默认值（除 `SECRET_KEY` 外）。
- 模块拆分**不改 API**：前端的 `/api/tasks`、`/api/submit-timesheet`、`/api/week-info`、`/login`、`/logout` 路径与响应格式 100% 保持。

### 决策 C：把"未登录"语义统一成 HTTP 401

当前所有 `/api/*` 失败都是 HTTP 200 + `{success: false}`，前端无法区分「业务失败」和「会话失效」。
拆分时顺手把"未登录"路径改成 `return jsonify({...}), 401`，前端加一个全局 fetch 拦截器：401 → 跳 `/`。这是 P1 修复能真正闭环的前提，不做的话用户还是只看到一个 toast。

## 3. 不做的事

- **不**引入 Redis / SQLAlchemy / Celery / Blueprint —— 与项目体量不匹配。
- **不**把 `RDMClient` 抽象成接口/Mock —— 没有测试需求驱动这个抽象。
- **不**改前端模板结构，只在 `dashboard.html` / `login.html` 的 JS 里加 401 拦截。
- **不**动 `archive/`（CLAUDE.md 明确只读）。

## 4. 影响与迁移

| 项目 | 影响 |
|---|---|
| 用户感知 | 改完之后，热重载/重启不再掉线；首次请求会因重登慢 1~2 秒，可接受 |
| `tools/` 脚本 | 不受影响（独立运行，不 import `app.py`） |
| 部署 | `start.bat` 增加 `set RDM_SECRET_KEY=...` 一行；缺失时 `app.py` 直接 raise，不再用弱默认 |
| 后续接 `get_my_tasks` / `submit_work_log` 真实端点 | 在 `rdm/client.py` 中实现，HTML 解析放 `rdm/parsers.py`，与路由解耦 |

## 5. 交付给研发的任务清单

按顺序执行，每步可独立提交：

1. **T-ARCH-001**：抽 `config.py`，`SECRET_KEY` 改为强制环境变量；`start.bat` 同步加默认值生成逻辑（首次启动写入随机值到本地文件）。
2. **T-ARCH-002**：按决策 B 拆 `app.py` 为 `rdm/client.py` + `web/routes.py` + `web/session_store.py` + `app.py`（入口）。**不改任何行为**，跑通登录 / 看到任务列表（虽然还是 stub）即算通过。
3. **T-ARCH-003**：实现决策 A 的"凭据回放"：`session` 多存一份加密密码；`get_client()` 自动重登；`/api/*` 失败用 HTTP 401。前端 `dashboard.html` 加 fetch 401 拦截 → 跳 `/`。
4. **T-ARCH-004**（验收）：手动测——登录 → dashboard → 改 `app.py` 触发热重载 → 不重新登录刷新 dashboard，任务列表仍能拉到。

研发开工前若发现 `RDMClient.login()` 的返回判断要变（比如重登场景下不应触发"登录成功"toast），先回到本 ADR 标注的"凭据回放"段落讨论后再改，不要在路由层加补丁。
