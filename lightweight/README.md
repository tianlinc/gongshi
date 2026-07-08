# IEI Timer Faster — 轻量版

## 概述

轻量版与桌面版功能完全相同（RDM 工时填报），区别在于：

- **轻量版**：启动后自动打开系统浏览器访问 `http://localhost:5000`，安装包约 150-200 MB
- **桌面版**：自带独立桌面窗口（pywebview + Edge WebView2），预打包 Chromium，安装包约 1.2 GB

## 构建

### 1. 安装依赖

```bash
cd lightweight
pip install -r requirements.txt
pip install pyinstaller
playwright install chromium
```

### 2. 打包

```bash
cd lightweight
build.bat
```

或手动执行：

```bash
pyinstaller --clean --noconfirm lightweight.spec
```

### 3. 产物

```
dist/IEI Timer Faster/IEI Timer Faster.exe  (~150-200 MB 未压缩)
```

## 分发

将 `dist/IEI Timer Faster/` 整个文件夹复制到目标电脑，双击 `IEI Timer Faster.exe` 启动。

## 首次运行说明

1. 双击 exe 后，程序自动下载 Playwright Chromium 浏览器组件（约 150 MB，仅首次需要）
2. 下载完成后打开系统默认浏览器到 `http://localhost:5000`
3. 如果在弹出 Windows 防火墙提示，请点击"允许"
4. 如果 5000 端口被占用，程序自动尝试 5001、5002

## 环境变量

| 变量名 | 说明 |
|--------|------|
| `GONGSHI_MIRROR_HOST` | Chromium 下载镜像地址，如 `http://10.111.36.3:8080` |

## 注意事项

- 轻量版使用系统浏览器，关闭浏览器窗口**不会**退出程序。停止程序请关闭控制台窗口或按 Ctrl+C
- Chromium 组件下载到 `%APPDATA%/gongshi/playwright-browsers/`，后续启动无需重新下载
- 不影响 `desktop/` 目录的桌面版构建，两者共用同一套 `app.py` / `templates/` / `static/`
