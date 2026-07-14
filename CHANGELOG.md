# CHANGELOG

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
