## 修复内容

**严重缺陷**：v1.2.0 / v1.2.1 安装后 `bootstrap.exe` 缺失，导致桌面快捷方式报 `CreateProcess 失败;错误代码2. 系统找不到指定的文件`，应用无法通过快捷方式启动。

**根因**：CI workflow（`.github/workflows/build.yml`）只构建了 `service.spec`（主应用），从未构建 `bootstrap.spec`（引导启动器）。本地 `build.bat` 在步骤 6 做了这件事，但 CI 中遗漏了。v1.2.0 将桌面快捷方式改为指向 `bootstrap.exe` 后，安装包里没有这个文件 → 快捷方式直接不可用。

**修复**：在 CI `build-windows` job 中，于确定性构建验证之后、manifest 生成之前，新增 `Build bootstrap launcher` 步骤：
1. `python -m PyInstaller --noconfirm bootstrap.spec` 编译 bootstrap.exe
2. 将 `dist/bootstrap.exe` 复制到 `dist/IEI Timer Faster/bootstrap.exe`
3. 验证复制成功

manifest.json 也会包含 `bootstrap.exe` 的 SHA256 哈希，确保增量更新方案能正确处理此文件。

## 变更文件

- `.github/workflows/build.yml` — 新增 `Build bootstrap launcher` 步骤（+18 行）
- `VERSION` — 1.2.1 → 1.2.2
- `RELEASE_NOTES.md` — 本文档
