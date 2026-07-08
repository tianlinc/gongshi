# RDM 工时填报系统 · 高保真原型

> 这是 **v2.2 需求文档** 配套的可点击仿真原型。**仅前端 + Mock 数据**，不连真实 RDM。
> 设计文档：[`../docs/design/v2-设计文档.md`](../docs/design/v2-设计文档.md)

## 启动方法

需要一个静态文件服务器（因为用 fetch 读 mock JSON，`file://` 协议会被浏览器拦截）。

```bash
# 在 prototype/ 目录下运行
cd prototype
python -m http.server 8000

# 浏览器打开
# http://localhost:8000/
```

任何静态服务器都行（`npx serve`、`http-server`、Nginx 等），不需要 Python 后端。

## 页面

| 路径 | 内容 |
| --- | --- |
| `/` 或 `index.html` | 登录页（A1–A6 记住账号） |
| `dashboard.html` | 工时主表（B / C / D / E / F） |
| `errors.html` | 错误形态集中演示（F1/F3/F4） |

## 推荐的体验路径

1. 打开 `/` → 勾选"记住我" → 任意账号密码登录（用户名 `fail` 会演示登录失败）
2. 关浏览器再重开 → 看到账号密码自动回填
3. 进入主表，留意：
   - 默认显示 5 行任务（不含已完成/已关闭的）
   - 任务名旁有 `负责` / `参与` / `负责·参与` 三种 badge
   - 默认是本周，标"本周" badge
4. 任意工时格输入 `25` → 自动 clamp 到 24，输入框红边
5. 顶部勾选 "启用周末" → 周六周日列变为可输入
6. 用日期选择器选 **2026-06-01** → 看到回填提示，三行任务已填入历史工时
7. 切回本周 → 点 "工作日填 8h" → 所有任务自动填好
8. 点 "提交本周工时" → 看到进度面板逐个任务串行提交
9. 找到 "故障演示用任务" 这一行，填上 2h 后再提交 → 看到 3 次重试 + 失败弹窗
10. 打开 `errors.html` 看 3 种错误演示

## Mock 数据怎么改

| 文件 | 用途 |
| --- | --- |
| `mock/tasks.json` | 任务列表，可改成自己的任务名；状态非 "未启动/进行中" 的会被过滤 |
| `mock/timesheet.json` | 旧周回填，key 是周一日期 `YYYY-MM-DD` |
| `mock/submit-result.json` | 提交结果模板（实际由 `app.js` 中 mockFetch 控制） |

修改后刷新页面即可生效，无需重启服务器。

## 给研发的接入提示

`assets/app.js` 顶部封装了 `mockFetch()` 拦截所有 `/api/*` 调用。研发对接真实后端时：

1. 把 `app.js` 里 `apiCall()` 中调的 `mockFetch` 改为浏览器原生 `fetch`
2. 后端 `/api/tasks` / `/api/timesheet?week_start=...` / `/api/submit-timesheet` 按 mock JSON 的形状返回即可
3. payload 字段已严格遵循 v2.2 §2.5 E2 的命名（snake_case + task_id 必带）

不要在原型里改 `app.py` 或加 Flask 路由——那是研发阶段的事。
