# CHANGELOG

## V1.1.11 (2026-07-15)

修复在线更新下载失败后无法重试、按钮状态错乱两个问题。

### 修复

- **下载重试机制**：`_do_download()` 重写为 retry loop，最多重试 2 次（间隔 2s）。覆盖 `IncompleteRead`/`ConnectionError`/`ChunkedEncodingError` 等网络异常，重试耗尽后提示"网络不稳定，下载失败，请重试"
- **按钮状态修复**：
  - 点击下载 → 按钮文案改为"正在下载..."，下载中隐藏按钮、显示进度条
  - 下载失败 → 按钮恢复为"下载更新"，可重新点击重试
  - 安装失败 → 按钮恢复为"下载更新"，可重新点击重试

## V1.1.10 (2026-07-14)

修复安装目录跳变的真正根因：ExpandConstant({GUID}) 两阶段转义链导致注册表查找静默失败。

### 修复

- **AppId 两阶段转义链根因修复**：`setup.iss` 的 `GetUninstallString()` 中 `ExpandConstant` + `{#emit SetupSetting("AppId")}` 形成两阶段转义链——ISPP 将 `{{GUID}}` 处理为 `{GUID}`（含花括号），然后 `ExpandConstant` 将 `{GUID}` 当作未知常量替换为空字符串，导致注册表路径被破坏（`_is1`），`IsUpgrade` 永远返回 `False`、安装器走全新安装路径
  - `setup.iss` AppId 改为**纯字符串** `A8F3C2B1-...`（无花括号）
  - `GetUninstallString` 注册表路径改为**字面量字符串**（无 ExpandConstant、无 {#emit}）
  - `_desktop_common.py` `KNOWN_APP_ID` 同步更新为无花括号纯字符串

### 文档

- **RELEASE_PROCEDURE.md**：新增踩坑 #9（ExpandConstant 未知常量吞并），附录二期望结果更新
- **RELEASE_CHECKLIST.md**：重写坑 #2 为两阶段转义链的完整描述

## V1.1.9 (2026-07-14)

V1.1.8 的修正版本，修复在线更新安装目录变化问题，更新发布流程文档。

### 修复

- **在线更新安装目录变化**：`restart_and_install()` 中 `target_dir` 改用 `sys.executable` 直接取当前进程目录，不再依赖注册表 AppId 查找。注册表查不到时 fallback 到硬编码默认路径导致安装目录改变（commit `07b07b0`）

### 文档

- **RELEASE_PROCEDURE.md**：新增踩坑 #8（在线更新 target_dir 来源），完整的现象/根因/修复/教训
- **RELEASE_CHECKLIST.md**：新增第 5 项检查——在线更新 `target_dir` 是否来自 `sys.executable`

## V1.1.8 (2026-07-14)

V1.1.7 的修正重建版本，无逻辑变更，仅修复 CI 编译配置使其可正确构建安装包。

### 修复

- **Inno Setup `AppId` 常量解析错误**：将 `{GUID}` 改为 `{{GUID}}`（Inno Setup 对字面量 `{` 的转义语法），修复 ISCC 编译 `Unknown constant` 错误
- **CI 错误遮蔽**：PyInstaller 和 ISCC 步骤增加 `|| exit /b %errorlevel%` 错误检查

## V1.1.7 (2026-07-14)

### 修复

- **RDM 自定义列导致任务名称识别为日期（INSPUR-93）**
  - 将 `_parse_a4j_tasks()` 从硬编码 td 索引改为内容特征识别（`span.item-span`、onclick 模式、日期正则），不再依赖列位置
  - 增加父任务自动过滤（`node-span` class 检测），避免无法填写工时的摘要行出现在任务列表中
  - 增加三级回退策略：当任务名列被彻底隐藏时，依次从链接 onclick 模式、非项目链接文字、纯文本中恢复任务名
  - 将 FC/CL 状态加入已知排除列表，不再打印"未知任务状态"警告

- **桌面应用限制单实例窗口（INSPUR-94）**
  - 基于 socket 端口绑定实现跨平台（Windows + Mac）单实例锁
  - 第二个实例启动时自动通知已有实例将窗口置前，然后退出
  - 通过 pywebview 窗口 API 实现 `on_top` 临时置顶 + 恢复，兼容 Edge WebView2
