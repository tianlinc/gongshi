# Windows 服务版打包

将 RDM 工时填报系统打包为 Windows 后台服务程序，双击 exe 即可启动 Flask 后端服务，用户通过系统浏览器访问 `http://127.0.0.1:5000`。

## 技术方案

采用 **PyInstaller onedir** 打包，与 `desktop/` 方案一致。

**服务版与桌面版的区别：**

| 项目 | 桌面版 (`desktop/`) | 服务版 (`service_installer/`) |
|------|--------------------|-------------------------------|
| 桌面窗口 | pywebview + Edge WebView2 | 无（用系统浏览器访问） |
| 凭证记忆 | 支持（AES 加密存储） | 不支持 |
| 加载页 | 首次启动显示 /init | 无 |
| CDN 改写 | Bootstrap/Icons 本地化 | 无 |
| 端口冲突 | 固定 5000 | 自动递增 5000→5001→5002 |
| Chromium 预打包 | 是 | 是 |
| 控制台窗口 | 无（console=False） | 无（console=False） |

## 文件说明

```
service_installer/
├── README.md             # 本文档
├── service_launcher.py   # 服务版启动器
├── service.spec          # PyInstaller spec 配置（核心）
├── requirements.txt      # 最小依赖清单
└── dist/                 # 构建产物（gitignore 建议）
    └── IEI Timer Faster Service/
        └── IEI Timer Faster Service.exe
```

## 快速开始

### 前置条件

- Windows 10/11
- Python 3.8+
- 已安装项目依赖：`pip install -r requirements.txt`

### 准备预打包浏览器（可选但推荐）

在打包前将 Playwright Chromium 预装到 `playwright-browsers-prebuilt/` 目录，这样最终用户无需联网下载。

```cmd
cd service_installer
set PLAYWRIGHT_BROWSERS_PATH=%CD%\playwright-browsers-prebuilt
python -m playwright install chromium
```

如果跳过此步骤，打包产物将不含预装 Chromium，用户首次启动时需联网下载（约 150MB）。

### 打包

```cmd
cd service_installer
pip install pyinstaller
pyinstaller --noconfirm service.spec
```

等待 2-5 分钟，输出在 `dist/IEI Timer Faster Service/IEI Timer Faster Service.exe`。

## 启动流程

1. 双击 `IEI Timer Faster Service.exe`
2. `service_launcher.py` 执行：
   - 初始化用户数据目录 `%APPDATA%/gongshi/`
   - 复制内置节假日缓存
   - 复制预打包 Chromium 浏览器到用户目录（首次，秒级）
3. 设置 `PLAYWRIGHT_BROWSERS_PATH` 环境变量
4. 从用户数据目录导入并启动 Flask（debug=False, host=127.0.0.1, 端口自动探测）
5. 在系统浏览器中访问 `http://127.0.0.1:5000` 即可使用

## 分发

将 `dist/IEI Timer Faster Service/` 整个文件夹复制到目标电脑，双击 exe。

### 注意事项

1. **启动后没有窗口**：服务版是纯后台 Flask 进程，需要手动打开浏览器访问 `http://127.0.0.1:5000`
2. **Windows 防火墙**：首次启动会触发防火墙弹窗，点击"允许访问"
3. **Chromium 已预打包**：首次启动仅需本地文件复制，无需联网下载
4. **RDM 内网访问**：需要能访问 `http://10.111.36.3:2029`
5. **端口冲突**：如果 5000 被占用，自动递增到 5001 或 5002
6. **日志文件**：`%APPDATA%/gongshi/run.log`

## 内网镜像加速

通过设置 `GONGSHI_MIRROR_HOST` 环境变量，可在 Chromium 首次下载时使用内网镜像：

```cmd
set GONGSHI_MIRROR_HOST=http://10.1.1.100:8080
```

## 常见问题

**Q: 启动后报错 "端口 5000/5001/5002 均被占用"？**
A: 关闭占用端口的程序后重试，或检查是否有旧实例未关闭。

**Q: 任务列表加载失败？**
A: Playwright Chromium 未正确初始化。检查 `%APPDATA%/gongshi/playwright-browsers/` 目录是否存在。

**Q: 登录后提示"网络异常"？**
A: 检查是否能访问 RDM 服务器 `http://10.111.36.3:2029`。

**Q: 怎么停止服务？**
A: 关闭命令行窗口（开发模式按 Ctrl+C），或在任务管理器中结束 `IEI Timer Faster Service.exe` 进程。
