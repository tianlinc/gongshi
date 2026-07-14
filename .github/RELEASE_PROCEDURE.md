# 软件版本发布步骤

本文档是"能直接照着执行"的标准发布流程，基于 V1.1.7 发布中踩过的所有坑编写。快速参考可看 [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md)。

---

## 一、v1.1.7 踩坑记录（禁止再犯）

### 坑 1：升级安装后版本号回退

**现象**：从 v1.1.6 升级到 v1.1.7 后关闭再打开，界面仍显示 v1.1.6。

**根因**：`setup.iss` 的 `[Files]` 使用 `Flags: ignoreversion`。`ignoreversion` 的含义是"目标路径已有同名文件则跳过"，`VERSION` 是纯文本无 Windows 版本资源，永远被跳过。旧 `VERSION`（内容 `1.1.6`）保留在原地。

**修复**：在 `[InstallDelete]` 段中，文件复制前先删除旧 `{app}\VERSION`。之后 `ignoreversion` 检查时目标不存在，新 VERSION 一定会写入。

```iss
[InstallDelete]
Name: "{app}\VERSION"
```

**教训**：`ignoreversion` 对有版本资源的文件（.exe/.dll）是安全的（只跳过旧版本），但对纯文本/纯数据文件是陷阱。

---

### 坑 2：`SaveStringToFile` → ISCC 编译失败

**现象**：CI 的 `upload-artifact` 报 `No files were found: IEI_Timer_Faster_Setup_*.exe`。

**表面原因**：找不到 .exe → 安装包没生成。

**真正根因**：`setup.iss` 的 `[Code]` 段使用了 `SaveStringToFile` 函数。这个函数是 **Inno Setup 6.0+ 才引入的 Pascal 支持函数**，CI 的 Chocolatey ISCC 版本不含此函数，编译报 Pascal 错误退出。更关键的是，build.yml 的 ISCC 命令**没有错误检查**，编译失败后静默继续，错误被 upload-artifact 的"No files found"完全遮蔽。

**修复**：
1. 移除 `SaveStringToFile`，改用 `[InstallDelete]` 实现相同效果
2. build.yml 的 ISCC 命令增加 `|| exit /b %errorlevel%` 让编译失败立即报错

```yaml
# build.yml
iscc "service_installer\installer\setup.iss" || exit /b %errorlevel%
```

**教训**：
- Inno Setup Pascal 函数有版本兼容性问题，用前查文档的最低版本要求
- CI 脚本中 `iscc` 编译命令**必须设置错误检查**（`|| exit /b`），否则编译失败会被后续步骤遮蔽
- `[InstallDelete]` 是纯 ISS 语法，无版本兼容性问题，优于 Pascal 代码

---

### 坑 3：AppId 单花括号 `{GUID}` → Inno Setup 常量解析失败编译中断

**现象**：ISCC 编译 abort，错误消息：

```
Error on line 33: Unknown constant "A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C".
Use two consecutive "{" characters if you are trying to embed a single "{" and not a constant.
Compile aborted.
```

**根因**：Inno Setup 将 `{...}` 解析为**内置常量**（如 `{app}`、`{src}`）。`AppId={A8F3C2B1-...}` 中的 `{` 被当作常量起始符，`A8F3C2B1-...` 不是已知常量名 → 编译失败。

**修复**：使用**双花括号 `{{...}}`**——这是 Inno Setup 的转义语法，"`{{`" 表示字面量 `{`，不触发常量查找：

```iss
AppId={{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}}
```

经过 Inno Setup 解析后，`AppId` 的值是字符串 `{A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C}`（含花括号）。

**教训**：
- **`{{...}}` 不是 ISPP 的"随机 GUID 生成指令"**——这是早期误判。ISPP 只处理 `{#...}` 开头的指令，不处理 `{{`
- `{{` 是 Inno Setup **自身**的转义语法（类似 C 语言 `\\` 转义为 `\`）
- 在 `[Setup]` 段等支持常量展开的区域，任何 `{Xxx}` 都会被当作常量查找。要用字面量花括号必须写 `{{`
- 常见混淆：`{#...}` 是 ISPP 预处理器语法（编译时求值），`{{` 是 Inno Setup 转义语法（运行时字面量）

---

### 坑 4：AppId 变化 → 全新安装而非覆盖安装

**现象**：用户从 v1.1.6 升级到 v1.1.7 后，磁盘上同时有 `IEI Timer Faster` 和 `IEI Timer Faster` 两个目录（或变到不同目录）。

**根因**：Inno Setup 靠 `AppId` 在注册表 (`HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\{AppId}_is1`) 中查找已有安装。AppId 不同 → 找不到旧记录 → 走全新安装路径，使用 `DefaultDirName` 的默认值而不会检测到旧安装目录。

**修复**：同坑 3，确保 AppId 在不同版本间固定不变。

**验证方法**：发布后找一台装过旧版本的机器升级安装，确认安装路径与旧版本一致，且旧目录被覆盖（非新增一个目录）。

---

### 坑 5：CI 触发条件是 `push tags: v*`

**现象**：commit 推送到 main 分支后，GitHub Actions 完全没有运行。

**根因**：`.github/workflows/build.yml` 的触发条件：

```yaml
on:
  push:
    tags: ['v*']
```

**只触发 tag push，不触发 branch push。** 推送到 main 分支不会启动工作流。

**修复**：每次提交后必须单独执行 `git tag -a vX.X.X ...` 和 `git push origin vX.X.X`。

**教训**：发布流程的步骤中，"创建 annotated tag"和"推送 tag"是两个必须单独执行的命令，不能以为 push commit 就自动触发 CI。

---

### 坑 6：`SO_REUSEADDR` → Windows 单实例锁失效

**现象**：打包为 EXE 后双击桌面图标，仍能打开多个窗口，单实例锁不生效。

**根因**：`_desktop_common.py` 的 `_acquire_instance_lock()` 使用了 `SO_REUSEADDR`：

```python
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
```

Windows Vista+ 和 Unix 对 `SO_REUSEADDR` 语义不同：
- **Unix（macOS/Linux）**：只允许重绑 TIME_WAIT 状态的端口，对正在 LISTENING 的 socket 不起作用，bind 会返回 `EADDRINUSE`
- **Windows Vista+**：如果两个进程都设置了 `SO_REUSEADDR` 并绑定同一个端口，内核**允许端口共享**。第二个实例的 `bind()` 成功，两个实例都认为自己是第一个

结果：第二个实例绑端口成功，跳过检查逻辑，直接创建新窗口。

**修复**：移除 `SO_REUSEADDR`。监听 socket（`listen()`）直接关闭时走 RST 而非 FIN，不进入 TIME_WAIT，不需要 `SO_REUSEADDR`。同时将异常路径的 `sys.exit(0)` 改为 `os._exit(0)`，绕过 atexit 钩子确保进程立即终止。

**教训**：`SO_REUSEADDR` 在 Windows 和 Unix 下行为根本不同，不能跨平台混用。Windows 上 `SO_REUSEADDR` 会导致端口劫持而非拒绝重复绑定。

---

### 坑 7：ISCC 参数引号 + PyInstaller 无错误检查 → 错误被 upload-artifact 多层遮蔽

**现象**：CI 的 upload-artifact 连续三次报 `No files were found: IEI_Timer_Faster_Setup_*.exe`，且每次被报告时已有"修复"。

**根因**：存在三层问题嵌套，任何一层修复都会使第二层暴露：

1. **PyInstaller 步骤无错误检查**：如果 PyInstaller 编译失败（如依赖缺失、spec 语法错误），`echo === Build done ===` 仍会打印，步骤标记为"成功"。ISCC 在下一步运行时找不到 `dist\IEI Timer Faster\*` 源文件。

2. **ISCC `/F` 和 `/O` 参数被 CMD 引号拆分**：
   ```
   /F"IEI_Timer_Faster_Setup_v%VERSION%"
   ```
   CMD 将以上拆分为两个参数：`/F` 和 `IEI_Timer_Faster_Setup_v%VERSION%`。取决于 ISCC 版本如何解析，`/F` 可能生效也可能被忽略。如果 `/F` 被忽略，ISCC 使用脚本中的 `OutputBaseFilename`（`IEI_Timer_Faster_Setup`）作为输出名，这与 upload-artifact 的模式 `IEI_Timer_Faster_Setup_*.exe`（有下划线+版本号）不匹配。

3. **upload-artifact 匹配模式过于严格**：`IEI_Timer_Faster_Setup_*.exe` 有下划线要求，默认文件名 `IEI_Timer_Faster_Setup.exe` 无法匹配。

**修复（commit `71d983e`）**：

- PyInstaller 步骤：加入 `|| exit /b %errorlevel%` + 输出文件存在性验证
- ISCC `/O`/`/F` 参数：去掉引号，使用无空格值 `"/FIEI_Timer_Faster_Setup_v%VERSION%"` → `/FIEI_Timer_Faster_Setup_v%VERSION%`（CMD 不会拆分）
- ISCC 步骤：编译后 `dir IEI_Timer_Faster_Setup*.exe` 确认输出存在，不存在则报错退出
- upload-artifact：模式改为 `IEI_Timer_Faster_Setup*.exe`（无下划线要求，匹配两种名称）
- create-release：同样更新文件模式

**教训**：
- CMD `|` block 中每条命令独立运行，前一条失败不等于步骤失败 —— 必须加 `|| exit /b %errorlevel%`
- ISCC CLI 参数值如果无空格，不要加引号。CMD 的 `"flag"value"` 语法会产生两个独立参数
- `upload-artifact` 的 `if-no-files-found: error` 只有在上游步骤成功时才触发 —— 它无法检测上游静默失败
- 防御式设计：生产出 exe 后立即用 `dir` 验证文件存在，不依赖后续 upload-artifact 报错

---

### 坑 8：在线更新 `target_dir` 来自注册表查找 → AppId 不匹配时掉到硬编码默认路径

**现象**：用户在 v1.1.7 安装目录（如 `D:\Tools\IEI Timer Faster`）点击在线更新升级到 v1.1.8，安装目录变成了 `%LOCALAPPDATA%\IEI Timer Faster`。

**根因**：`_desktop_common.py` 的 `restart_and_install()` 虽然传了 `/DIR="{target_dir}"`，但 `target_dir` 的来源是 `_get_windows_install_dir()`（注册表查 InstallLocation）。注册表查找依赖 `KNOWN_APP_ID` 匹配，AppId 变更或权限问题导致查找失败时返回 None，`target_dir` 直接 fallback 到硬编码的 `LOCALAPPDATA\IEI Timer Faster`。

**修复**（commit `07b07b0`）：在注册表查找前增加 `sys.executable` 作为最高优先级：

```python
import sys

frozen_dir = None
if getattr(sys, 'frozen', False):
    frozen_dir = os.path.dirname(sys.executable)

install_dir = frozen_dir or self._get_windows_install_dir()
```

在线更新时 PyInstaller frozen 进程的 `sys.executable` 就是 `IEI Timer Faster.exe` 的完整路径，`os.path.dirname()` 直接得到安装目录——**不依赖注册表、不依赖 AppId 历史、永远正确**。

注册表兜底保留给开发调试（`python app.py` 非 frozen 模式）。

**教训**：
- `target_dir` 必须从**当前运行的进程路径**获取（`sys.executable`），而不是从外部注册表查询——更新进程自身所在目录就是最准确的目标路径
- 注册表查找适合**首次安装**场景（安装器需要知道"以前装过没"），不适合**运行时更新**场景（进程已经在目标目录下运行了）
- `/DIR=` 传了不代表传的是正确值——要查来源追溯链

**验证方法**（commit `07b07b0` `_desktop_common.py:788-796`）：
```python
# frozen 模式下 frozen_dir 应非 None，且等于应用程序实际安装目录
assert frozen_dir is not None  # PyInstaller 打包后运行
assert target_dir == frozen_dir  # 不走注册表 fallback
```

---

### 坑 9：`ExpandConstant({GUID})` → 未知常量替换为空字符串 → 注册表查找失败 → 安装目录跳变

**现象**：安装 v1.1.9 后安装目录仍然变化，不是期望的旧目录。这已经是第五次。

**根因**：`setup.iss` 的 `GetUninstallString()` 用了 `ExpandConstant` + `{#emit SetupSetting("AppId")}` 组合：
```pascal
sUnInstPath := ExpandConstant('...\Uninstall\{#emit SetupSetting("AppId")}_is1');
```

这形成了一个**两阶段转义链**：
1. ISPP 阶段：`SetupSetting("AppId")` 返回 `{{A8F3C2B1-...}}` → `{#emit}` 处理 `{{` 为 ISPP 转义 → 发射 `{A8F3C2B1-...}`（含花括号）
2. Inno Setup 运行时：`ExpandConstant` 遇到 `{A8F3C2B1-...}` → 不是已知常量（`{app}`、`{src}` 等）→ **替换为空字符串**
3. 注册表路径变成 `Software\...\Uninstall\__is1`（GUID 被吞）
4. `RegQueryStringValue` 找不到 → `GetUninstallString` 返回 `''`
5. `IsUpgrade` 返回 `False` → 安装器走全新安装路径 → 默认目录

**修复**（commit 未定）：AppId 改为纯字符串（无花括号）、Pascal 代码用字面量路径（无 ExpandConstant + #emit）：

```iss
; setup.iss
AppId=A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C       ; ← 纯字符串，无花括号
sUnInstPath := '...\Uninstall\A8F3C2B1-..._is1';  ; ← 字面量路径，无 ExpandConstant
```

```python
# _desktop_common.py
KNOWN_APP_ID = 'A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C'  # ← 无花括号
```

**教训**：
- `ExpandConstant` + `{#emit SetupSetting("AppId")}` 组合是危险的——会经过 ISPP 转义 → Inno Setup 常量解析两层处理，任一层出错都会导致注册表查找失败
- AppId 应使用纯字符串（无花括号），既避免 `[Setup]` 段的常量查找，也避免 `ExpandConstant` 的未知常量吞并
- 当 AppId 出现在 Pascal 代码的注册表路径中时，直接用字面量字符串，不要用 `ExpandConstant` 或 `{#emit}`
- 原始 AppId `{{A8F3C2B1-...}`（缺失一个 `}`）从初始 commit 起就存在，不同 ISCC 版本处理方式不同，长期不一致

**验证方法**：安装包编译后检查 `setup.iss` 中 `AppId` 是纯字符串 `A8F3C2B1-...`（无花括号），`GetUninstallString` 中是字面量路径（无 `ExpandConstant`、无 `{#emit}`）。

---

## 二、发布标准流程

以下步骤应**逐条执行，不可跳过**。每条标有 **[必须]** 的是强制性检查。

### 第 1 步：准备工作 —— 修改版本号

**[必须]** 修改项目根目录的 **`VERSION`** 文件，将版本号改为新版本（如 `1.1.8`）。

`VERSION` 是本项目**唯一的版本号数据源**，不存在其他硬编码版本号。9 处读取位置详见 [附录一](#附录一版本号关联位置汇总)。

**[必须]** 编辑 **`CHANGELOG.md`**，在文件顶部新增版本条目，格式参考已有条目。

**检查清单**（修改完成后逐条确认）：

| # | 检查项 | ✓ |
|---|--------|---|
| 1 | `VERSION` 文件内容为新版本号，无多余空格/空行 | |
| 2 | `CHANGELOG.md` 顶部已有新版本条目，描述了所有变更 | |
| 3 | 没有修改任何其他文件中的版本号硬编码（不应该存在） | |

---

### 第 2 步：本地最终审查

**[必须]** 在提交前，确认编译配置无误：

```bash
# 检查 setup.iss 关键配置
grep -n "AppId\|AppVersion\|AppName\|\#define MyApp" service_installer/installer/setup.iss
```

**检查清单**：

| # | 检查项 | ✓ |
|---|--------|---|
| 1 | `AppId` 使用纯字符串 `A8F3C2B1-...`（无花括号，无 `{{}}` 转义，无 ISPP/IS 处理） | |
| 2 | `AppVersion` 读取自 `VERSION` 文件（`{#MyAppVersion}` 宏），无硬编码 | |
| 3 | `AppName` = `{#MyAppName}`，无硬编码 | |
| 4 | `[InstallDelete]` 段包含 `{app}\VERSION` 条目 | |
| 5 | `[Code]` 段**没有** `SaveStringToFile`（ISCC 6.0+ 函数，Chocolatey 不兼容） | |
| 6 | ISCC `/O` 和 `/F` 参数值**不带引号**（如 `/Opath` 非 `/O"path"`），避免 CMD 参数拆分 | |

---

### 第 2b 步：本地验证 ISCC 编译通过

**[必须]** 在 push 前，本地执行 ISCC 编译确认配置无误：

```bash
# 1. 切换到 setup.iss 所在目录执行（保证相对路径正确）
cd service_installer\installer

# 2. 运行 ISCC 编译（调试模式，输出详细日志）
ISCC.exe setup.iss

# 3. 检查编译结果
echo %errorlevel%    # 必须为 0
dir ..\dist\IEI_Timer_Faster_Setup*.exe  # 确认 exe 已产出
```

**编译通过的标准**：
- 返回码 `%errorlevel%` = 0
- `service_installer\dist\` 下有 `IEI_Timer_Faster_Setup.exe` 或 `IEI_Timer_Faster_Setup_v*.exe`
- 日志中无 `Error` 或 `[FAIL]` 字样

**如果本地没有 ISCC**：
1. 安装 Inno Setup 6：`choco install innosetup`（模拟 CI 的 Chocolatey 安装方式）
2. 或从 [jrsoftware.org](https://jrsoftware.org/isdl.php) 官网下载安装
3. 安装后在 `C:\Program Files (x86)\Inno Setup 6\` 找到 `ISCC.exe`，加入 PATH 或使用完整路径

**如果首次编译缺少中文语言包**：
```bash
curl -o "C:\Program Files (x86)\Inno Setup 6\Languages\ChineseSimplified.isl" https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl
```

**编译不过的常见原因排查**：

| 错误 | 可能原因 | 解决 |
|------|----------|------|
| `File not found: ..\..\VERSION` | ISPP 读取 VERSION 失败 | 检查 VERSION 文件是否存在、路径是否正确 |
| `File not found: ..\dist\IEI Timer Faster\*` | PyInstaller 还没构建 | 先跑 `pyinstaller service.spec` 再跑 ISCC |
| `Duplicate identifier` / `undeclared identifier` | setup.iss 语法错误 | 检查 `#define`、`[Code]` 段语法 |
| `SaveStringToFile` undefined | 用了 ISCC 6.0+ 函数 | 删除该调用，改用 `[InstallDelete]` |
| `AppId` 相关警告 / `Unknown constant` 错误 / 安装目录变化 | 使用了花括号 `{`/`{{...}}` 触发 Inno Setup/ISPP 转义链 | 改为纯字符串 `A8F3C2B1-...`（无花括号），`GetUninstallString` 用字面量路径 |

**此步骤验证通过后才能继续下一步。** 如果在后续 push 后 CI 仍失败，这步必须重新执行。

---

### 第 3 步：Commit 并 Push 主分支

```bash
git add VERSION CHANGELOG.md <其他所有改动的文件>
git commit -m "release: Vx.x.x <一句话描述>"
git push
```

**[必须]** `git push` 后确认输出 `... main -> main` 且无错误。

---

### 第 4 步：创建并推送 Annotated Tag

**这是最重要的一步 —— CI 构建由此触发。**

```bash
git tag -a vx.x.x -m "Vx.x.x: <简要描述>"
git push origin vx.x.x
```

> 实际上可简化为两步：
> ```bash
> git tag -a v1.1.9 -m "V1.1.9: <描述>" && git push origin v1.1.9
> ```

**[必须]** tag 类型是 **annotated** (`-a`)，不是 lightweight。`git push` 后确认输出 `* [new tag] vx.x.x -> vx.x.x`。

**检查清单**：

| # | 检查项 | ✓ |
|---|--------|---|
| 1 | Tag 已推送（`git ls-remote --tags origin | grep vx.x.x` 有输出） | |
| 2 | Tag 指向最新 commit（与步骤 3 的 commit hash 一致） | |

---

### 第 5 步：监控 CI 构建

1. 打开 GitHub 仓库 → Actions → Build workflow
2. 确认名称为 `vx.x.x` 的 Workflow Run 已自动触发
3. 等待 **build-windows**、**build-macos**、**create-release** 全部完成（绿色 ✓）

**如果任何 Job 失败**：
- 先看 `build-windows` → 展开 `ISCC Compile Installer` 步骤的日志
- 常见问题：
  - `No files were found for upload-artifact` → ISCC 编译失败了，`|| exit /b` 没加导致被遮蔽
  - Pascal 错误 → `[Code]` 段用了不兼容的函数（如 `SaveStringToFile`）
  - ISPP 错误 → 预处理阶段失败，检查 `setup.iss` 语法

**[必须]** 确认 **create-release** Job 完成后，在仓库的 Releases 页面能看到新版本的安装包。

---

### 第 6 步：验证安装包（升级安装）

**[必须]** 在至少一台**安装了旧版本的机器**上做升级安装验证。如果本地没有旧版本环境，先在 CI 下载旧版本安装包部署。

#### 6a. 版本号验证

| # | 验证项 | 步骤 | 预期结果 |
|---|--------|------|----------|
| 1 | 安装后版本号正确 | 覆盖安装 → 启动应用 → 查看界面左下角 | 显示新版版本号，不是旧版 |
| 2 | 重启后版本号不变 | 关闭应用 → 重新打开 | 仍然显示新版版本号 |

#### 6b. 安装目录验证

| # | 验证项 | 步骤 | 预期结果 |
|---|--------|------|----------|
| 1 | 安装目录不变 | 记下旧版本安装目录 → 升级安装 → 查看安装目录 | 安装目录与旧版本一致 |
| 2 | 未出现多版本 | 检查旧目录路径 | 只有一个版本，旧目录被覆盖 |

#### 6c. 单实例锁验证

| # | 验证项 | 步骤 | 预期结果 |
|---|--------|------|----------|
| 1 | 双击不重复打开 | 启动应用 → 再次双击桌面图标或 exe | 已有窗口被拉到前台，不出现第二个窗口 |
| 2 | 快捷方式启动 | 从桌面快捷方式双击启动 | 同 1 |

#### 6d. 核心功能冒烟

| # | 验证项 | 步骤 | 预期结果 |
|---|--------|------|----------|
| 1 | 登录正常 | 输入 RDM 账号密码登录 | 登录成功，跳转到填报页面 |
| 2 | 任务加载 | 打开后任务列表自动加载 | 任务正确显示，无日期误识别 |
| 3 | 工时提交 | 填写一周工时并提交 | 提交成功，无错误 |

---

### 第 7 步：完成发布

全部验证通过后：

1. 在 GitHub Releases 页面编辑 Release，补充发布说明（从 CHANGELOG.md 复制）
2. 通知用户下载新版本

---

## 三、失败回滚指南

如果 CI 构建失败或发布后发现严重问题，按以下步骤处理：

### 重新打 Tag（修复代码后）

```bash
# 1. 修复代码，commit + push
git add .
git commit -m "fix: <修复描述>"
git push

# 2. 删除旧 tag（本地 + 远程）
git tag -d vx.x.x
git push origin :refs/tags/vx.x.x

# 3. 在新 commit 上重新创建 annotated tag 并推送
git tag -a vx.x.x -m "Vx.x.x: <描述>"
git push origin vx.x.x
```

> **不会删除远程 Release**：GitHub Release 是独立实体，删除 tag 后 Release 变成"Draft"状态且不与任何 tag 关联。但旧 Release 中的安装包可能仍可下载，建议手动编辑旧 Release 标记为过时或删除。

### Tag 已经推送但还没推送，可以撤销

推送 tag 前要确认无误。如果 tag 已推送但 ci 还没跑完：

1. 如果 CI 刚开始跑 → 删除远程 tag（上面的步骤 2）
2. 如果 Release 已经创建且有用户下载了 → 发修复版本（如 v1.1.7a 或 v1.1.8），不要覆盖同一版本号的安装包

---

## 附录一：版本号关联位置汇总

修改版本号时只需改 `VERSION` 文件，以下 9 处**自动读取**，无需手动修改：

| # | 位置 | 读取方式 | 用途 |
|---|------|----------|------|
| 1 | `app.py:49-56` | 运行时 `open(VERSION).read()` | `/api/version`、`/api/system-info` 接口 |
| 2 | `_desktop_common.py:101-113` | 运行时 `open(VERSION).read()` | 启动横幅、`/init` 页面、更新检查 |
| 3 | `service_installer/service.spec:48` | PyInstaller `datas=[('../VERSION', '.')]` | 打包时复制 VERSION 到产物根目录 |
| 4 | `service_installer/service.spec:147` | 构建时 `open(VERSION).read()` | macOS `.app` Bundle 版本号元数据 |
| 5 | `service_installer/build.bat:155-161` | 构建时 `set /p VERSION=<..\\VERSION` | 安装包文件名 `IEI_Timer_Faster_Setup_vx.x.x.exe` |
| 6 | `service_installer/installer/setup.iss:19-25` | `#include "../VERSION"` → `{#MyAppVersion}` | Inno Setup 安装器版本号 |
| 7 | `service_installer/installer/setup.iss:78-79` | `[InstallDelete]` 段 `{app}\VERSION` | 升级安装时删除旧 VERSION，配合 `ignoreversion` 确保新版本号一定写入 |
| 8 | `tools/generate_appcast.py:32-34` | CI 构建时 `open(VERSION).read()` | Sparkle 更新检测 appcast.xml |
| 9 | `.github/workflows/build.yml:76` | CI `$VERSION = Get-Content VERSION` | Release 安装包命名 |

---

## 附录二：setup.iss 关键配置自查

每次发布前用以下命令快速检查 `setup.iss` 关键配置：

```bash
# Windows
grep -n "^AppId\|^AppVersion\|^AppName\|^DefaultDirName" service_installer\installer\setup.iss
grep -n "InstallDelete" service_installer\installer\setup.iss
grep -n "SaveStringToFile" service_installer\installer\setup.iss
```

期望结果：
- `AppId=A8F3C2B1-9D4E-5F6A-7B8C-0D1E2F3A4B5C`（**纯字符串，无花括号**——消除 ISPP/Inno Setup 转义链）
- `AppVersion={#MyAppVersion}`（编译时宏）
- `[InstallDelete]` 段存在，含 `{app}\VERSION`
- `SaveStringToFile` **不应出现**（如出现需删除并改为 `[InstallDelete]`）
- `[Code]` 段 `GetUninstallString` 中注册表路径为字面量字符串（无 `ExpandConstant`、无 `{#emit}`）
