# RDM 工时填报系统

一个 Web 化的 RDM 研发管理平台（`http://10.111.36.3:2029`）工时填报工具。
用浏览器一次性填一周工时，比在 RDM 原生界面里一格格点要快得多。

## 当前状态

- ✅ **登录** — AES 加密认证已对接，输入账号密码即可登录
- ✅ **界面** — 一周七天 × 多任务的批量填写表格，支持草稿、预览、模板
- ⏳ **任务同步** — 后端 `RDMClient.get_my_tasks()` 当前返回示例数据，待对接
- ⏳ **工时提交** — 后端 `RDMClient.submit_work_log()` 当前为打印演示，待对接

## 启动

```bash
# 安装依赖（首次）
pip install flask flask-cors requests pycryptodome beautifulsoup4

# 启动
python app.py
# 或双击 start.bat

# 浏览器访问
http://localhost:5000
```

## 目录结构

```
gongshi/
├── app.py              # Flask 主程序（RDMClient + 路由）
├── start.bat           # 一键启动脚本
├── templates/          # 前端页面
│   ├── login.html      # 登录页
│   └── dashboard.html  # 工时填写主页
├── tools/              # 探测脚本和抓到的页面样本
│   ├── explore.py      # 自动探测 RDM 系统菜单/接口
│   ├── test_pages.py   # 直接拉取已知关键页面
│   └── *.html          # 已抓到的页面（main / myTask / workLogList）
├── docs/               # 详细文档
└── archive/            # 旧版本（v1，仅供参考）
```

## 关键发现（已通过探测确认）

登录端点和加密方式：

- 登录页：`GET /index.jsp`
- 提交：`POST /j_security_check`
- 字段：`j_username`、`j_password`，两者都是 **先 base64 再 AES-ECB 加密**
- AES key（硬编码在 `/scripts/index.js`）：`abcdefgabcdefg12`

任务/工时相关页面（从 `main.do` 菜单 HTML 中提取）：

- 我的任务：`/pages/task/list/myTask.jsf`
- 工作日志：`/pages/myspace/log/workLogList.jsf`
- 任务类型切换（页面内 radio）：
  - `myRecive` → 我负责的任务
  - `myReciveActor` → 我参与的任务
  - `myAssign` → 我分配的任务
  - `myAudit` → 待我审核的任务

## 下一步对接

要把示例数据换成真接口，需要补两件事：

1. **任务列表抓取** — `myTask.jsf` 是 JSF 页面，任务表格由 `tableMain` 通过 AJAX 加载。
   下一步用浏览器 F12 抓真实请求（URL + payload），改写 `RDMClient.get_my_tasks()`。
2. **工时提交** — 同样需要在 RDM 里手动填一次工时，抓 `workLogList.jsf` 上的提交请求，
   改写 `RDMClient.submit_work_log()`。

`tools/explore.py` 可重新跑一次拉取最新的菜单 HTML，`tools/test_pages.py` 直接拉指定页面。

## 详细文档

- `docs/使用说明.md` — 完整使用指南、配置项、FAQ
- `docs/完整说明-用户版.md` — 给最终用户的快速上手版
