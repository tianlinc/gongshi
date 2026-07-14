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
| `service_installer/installer/setup.iss:163-168` | 运行时写入 `MyAppVersion` | `ssPostInstall` 强制写入 VERSION 文件 |
| `tools/generate_appcast.py:32-34` | CI 构建时读取 `VERSION` | Sparkle 更新检测 appcast.xml |
| `.github/workflows/build.yml:76` | CI 构建时读取 `VERSION` | 安装包命名 |

## 常见坑

### 1. 升级安装后版本号不更新

**根因**：Inno Setup 的 `ignoreversion` 标志会在升级时跳过已存在的同名文件，导致旧版 `VERSION` 文件不被覆盖。

**修复**（`setup.iss:163-168`）：在 `ssPostInstall` 步骤中使用 `SaveStringToFile` 强制写入最新版本号。此修复已于 V1.1.7 加入，新版本不会再出现此问题。

### 2. 忘记推送 Tag → CI 不触发

`build.yml` 的触发条件是 `push tags v*`，不是 `push branch main`。Commit 推送到 main 后**必须另外创建并推送 tag**。

### 3. VERSION 文件带有 BOM 或多余换行

确保 `VERSION` 文件内容为纯文本单行（如 `1.1.7`），末尾可以有换行。`_read_version()` 和 `_read_app_version()` 均使用 `.strip()` 处理，可容忍尾部空白。
