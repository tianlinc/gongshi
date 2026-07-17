## 修复内容

**问题**：v1.1.15 ~ v1.1.17 版本在线升级完成后不会自动重启应用，用户需要手动双击 exe 才能打开新版本。

**根因**：在线升级的批处理脚本由**当前运行版本**的 `_desktop_common.py` 生成。v1.1.15 版本的批处理脚本中包含用于创建桌面快捷方式的 PowerShell `^` 多行续行，这些 `^` 字符在 GBK 编码批处理的 `if` 块内会触发解析错误，导致批处理直接崩溃退出——`start "" "new.exe"` 命令永远不执行。

更棘手的是：v1.1.17 虽然已在 `_desktop_common.py` 中移除了这部分 PowerShell 代码，但用户从 v1.1.16 升级到 v1.1.17 时，批处理仍由 v1.1.16 的旧代码生成，崩溃依然发生。这是一个鸡生蛋问题——`_desktop_common.py` 的修复在当前升级周期内无法惠及用户。

**修复方案（防御设计）**：在 `setup.iss` 中增加 `[Run]` 段，让 Inno Setup installer 自身在静默安装完成后直接启动新版本 exe。这是 installer（本次安装的新版本二进制）自己的行为，**不依赖**旧版本的批处理脚本。即使旧版批处理崩溃，installer 仍能成功启动应用。

```
[Run]
; 正常安装：完成页显示"启动应用"复选框
Filename: "{app}\IEI Timer Faster.exe"; Description: "启动 IEI Timer Faster"; Flags: nowait postinstall skipifsilent
; 静默升级：自动启动新版本
Filename: "{app}\IEI Timer Faster.exe"; Flags: nowait shellexec; Check: IsSilentInstall
```

- `Check: IsSilentInstall` — 仅静默升级（`/VERYSILENT`）时执行，正常安装不受影响
- `shellexec` — 作为独立进程启动，与 installer 生命周期解耦，不会因 installer 退出而终止
- `nowait` — 不等待新应用退出，安装流程正常结束

## 验证过程

1. 用 v1.1.17 的 `_desktop_common.py` 按实际路径参数生成批处理脚本，逐行检查：
   - 无 `^` 续行，无 `/B` 标志，无 PowerShell 代码，`start ""` 命令存在
2. 构造相同结构的测试批处理，运行后所有日志行正常写入，`start` 命令成功执行
3. 确认 `[Run]` 段中 `Check: IsSilentInstall` 引用的函数已在 `setup.iss` 的 `[Code]` 段中正确定义

## 变更文件

- `service_installer/installer/setup.iss` — 新增 `[Run]` 段（+10 行）
