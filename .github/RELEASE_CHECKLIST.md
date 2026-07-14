# 发布/升级 Checklist

发布新版本时，按以下顺序操作，确保版本号在所有位置同步更新。

## 1. 修改版本号（单文件）

修改项目根目录的 **`VERSION`** 文件，将版本号改为新版本（如 `1.1.8`）。

> `VERSION` 是本项目**唯一的版本号数据源**。以下所有位置均直接或间接读取此文件，不应存在其他硬编码版本号。

## 2. 更新 CHANGELOG

编辑 **`CHANGELOG.md`**，在文件顶部新增版本条目，记录本版变更。

## 3. Commit 并 Push

```bash
git add VERSION CHANGELOG.md <其他修改的文件>
git commit -m "release: Vx.x.x VERSION=x.x.x"
git push
```

## 4. 创建并推送 Annotated Tag

**⚠️ CI/CD 构建由 tag push 触发**（`.github/workflows/build.yml` 的触发条件是 `on.push.tags: ['v*']`）。

```bash
git tag -a v1.1.8 -m "V1.1.8: <简要描述变更>"
git push origin v1.1.8
```

> 只 push commit 不会触发构建，必须 push tag。

## 5. 验证 CI 构建

1. 打开 GitHub Actions 页面
2. 确认 `Build` workflow 已自动触发
3. 等待 `build-windows`、`build-macos`、`create-release` 全部通过
4. 在 Releases 页面确认新版本安装包已生成

## 版本号读取位置汇总

以下位置依赖 `VERSION` 文件，修改版本号时**无需手动修改**（均自动读取）：

| 位置 | 读取方式 | 用途 |
|------|----------|------|
| `app.py:49-56` | 运行时读取 `VERSION` 文件 | `/api/version`、`/api/system-info` 接口 |
| `_desktop_common.py:101-113` | 运行时读取 `VERSION` 文件 | 启动横幅、`/init` 页面、更新检查 |
| `service_installer/service.spec:48` | `('../VERSION', '.')` | PyInstaller 打包时复制 VERSION 到产物根目录 |
| `service_installer/service.spec:147` | 构建时读取 `VERSION` 文件 | macOS `.app` Bundle 版本号元数据 |
| `service_installer/build.bat:155-161` | 构建时读取 `VERSION` 文件 | 安装包文件名 `IEI_Timer_Faster_Setup_vx.x.x.exe` |
| `service_installer/installer/setup.iss:19-25` | 编译时读取 `VERSION` 文件 | Inno Setup 安装器版本号 `MyAppVersion` |
| `service_installer/installer/setup.iss:78-79` | `[InstallDelete]` 在复制前删除旧 VERSION | 配合 `ignoreversion` 确保新 VERSION 总能写入 |
| `tools/generate_appcast.py:32-34` | CI 构建时读取 `VERSION` | Sparkle 更新检测 appcast.xml |
| `.github/workflows/build.yml:76` | CI 构建时读取 `VERSION` | 安装包命名 |

## 常见坑

### 1. 升级安装后版本号不更新

**根因**：Inno Setup 的 `ignoreversion` 标志会在升级时跳过已存在的同名文件，导致旧版 `VERSION` 文件不被覆盖。

**修复**（`setup.iss`）：使用 `[InstallDelete]` 在文件复制前删除旧 `VERSION` 文件，配合 `ignoreversion` 的"目标不存在即复制"逻辑，新 VERSION 总能写入。此修复已于 V1.1.7 加入。

### 2. AppId 使用 `{GUID}` 单花括号 → Inno Setup 常量解析失败编译中断

**现象**：ISCC 编译 abort，错误消息：
```
Error on line 33: Unknown constant "A8F3C2B1-..."
Use two consecutive "{" characters if you are trying to embed a single "{" and not a constant.
Compile aborted.
```

**根因**：Inno Setup 将 `{...}` 解析为内置常量。`AppId={GUID}` 中的 `{` 被当作常量起始符，`GUID` 字符串不是已知常量名 → 编译失败。

**修复**（`setup.iss`）：必须使用**双花括号 `{{GUID}}`**——Inno Setup 自己的转义语法，`{{` 表示字面量 `{`，不触发常量查找。解析后 `AppId` 值为字符串 `{A8F3C2B1-...}`。

> **`{{...}}` 不是 ISPP 的"随机 GUID 生成指令"**——这是早期误判。ISPP 只处理 `{#...}` 开头的指令，`{{` 完全是 Inno Setup 自身的转义语法。此修复已于 V1.1.7 加入。

### 3. 忘记推送 Tag → CI 不触发

`build.yml` 的触发条件是 `push tags v*`，不是 `push branch main`。Commit 推送到 main 后**必须另外创建并推送 tag**。

### 4. VERSION 文件带有 BOM 或多余换行

确保 `VERSION` 文件内容为纯文本单行（如 `1.1.7`），末尾可以有换行。`_read_version()` 和 `_read_app_version()` 均使用 `.strip()` 处理，可容忍尾部空白。

### 5. 在线更新 `target_dir` 来自注册表查找 → 安装目录变化

**现象**：在线更新升级后安装目录改变，切到了 `%LOCALAPPDATA%\IEI Timer Faster`。

**根因**：`_desktop_common.py` `restart_and_install()` 的 `target_dir` 来自 `_get_windows_install_dir()`（注册表查 InstallLocation），注册表查不到时 fallback 到硬编码默认路径。

**修复**（commit `07b07b0`）：使用 `sys.executable`（frozen 模式）作为最高优先级——更新进程本身就在安装目录下，不需要注册表。

**验证**：检查 `_desktop_common.py` 的 `restart_and_install()` 中 `target_dir` 的确定逻辑：
```python
# 必须存在这段逻辑（commit 07b07b0+）
frozen_dir = None
if getattr(sys, 'frozen', False):
    frozen_dir = os.path.dirname(sys.executable)
install_dir = frozen_dir or self._get_windows_install_dir()
```
