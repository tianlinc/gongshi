# IEI Timer Faster 桌面版打包

INSPUR-74: 从 Windows 后台服务（NSSM）改造为独立桌面应用。用户双击快捷方式即可在 WebView2 窗口中访问，无需系统浏览器。

## 技术方案

采用 **PyInstaller onedir** + **pywebview + Edge WebView2** 打包。

## 文件说明

```
service_installer/
├── README.md             # 本文档
├── service_launcher.py   # 桌面版启动器（pywebview + WebView2）
├── service.spec          # PyInstaller spec 配置（核心）
├── build.bat             # 一键构建（PyInstaller + Inno Setup）
├── requirements.txt      # 依赖清单（含 pywebview）
├── installer/
│   ├── setup.iss         # Inno Setup 安装脚本（桌面版）
│   └── iei_timer.ico     # 程序图标
└── dist/                 # 构建产物（gitignore 建议）
    ├── IEI Timer Faster/
    │   └── IEI Timer Faster.exe    (~700MB 含 Chromium)
    └── IEI_Timer_Faster_Setup.exe  (安装包)
```

## 快速开始

### 前置条件

- Windows 10 21H2+ / Windows 11（Edge WebView2 内置于系统）
- Python 3.8+
- 已安装项目依赖：`pip install -r requirements.txt`

### 一键构建（推荐）

```cmd
cd service_installer
build.bat
```

自动完成：Python/PyInstaller/pywebview/Playwright 检查 → Chromium 预置 → PyInstaller 打包 → Inno Setup 安装包编译。

### 手动打包

```cmd
cd service_installer
pip install pyinstaller
pyinstaller --noconfirm service.spec
```

### 开发调试

```cmd
cd service_installer
python service_launcher.py
```

开发模式下会启动 Flask debug 服务器并自动打开系统浏览器。

## 启动流程

1. 双击 `IEI Timer Faster.exe`（或桌面快捷方式）
2. `service_launcher.py` 执行：
   - 初始化用户数据目录 `%APPDATA%/gongshi/`
   - 复制内置节假日缓存
   - 复制预打包 Chromium 浏览器到用户目录（首次，秒级）
3. Flask 在后台线程启动（debug=False）
4. 打开 pywebview 桌面窗口 → 加载 `http://127.0.0.1:<port>`
5. 关闭桌面窗口 → Flask 进程自动退出

## 分发

### 方式 1：安装包（推荐）

运行 `IEI_Timer_Faster_Setup.exe`，按照向导安装：
- 自动创建桌面快捷方式
- 安装路径：`%LOCALAPPDATA%\IEI Timer Faster`
- 卸载：控制面板 → 程序和功能 → IEI Timer Faster

### 方式 2：绿色版

将 `dist/IEI Timer Faster/` 整个文件夹复制到目标电脑，双击 exe。

### 注意事项

1. **独立窗口**：应用在 pywebview 窗口中运行，不依赖系统浏览器
2. **Windows 防火墙**：首次启动会触发防火墙弹窗，点击"允许访问"
3. **Chromium 已预打包**：首次启动仅需本地文件复制，无需联网下载
4. **RDM 内网访问**：需要能访问 `http://10.111.36.3:2029`
5. **端口冲突**：如果 5000 被占用，自动递增到 5001 或 5002
6. **日志文件**：`%APPDATA%/gongshi/run.log`
7. **凭证记忆**：登录密码 AES 加密存储在 `%APPDATA%/gongshi/credentials.dat`

## 内网镜像加速

通过设置 `GONGSHI_MIRROR_HOST` 环境变量，可在 Chromium 首次下载时使用内网镜像：

```cmd
set GONGSHI_MIRROR_HOST=http://10.1.1.100:8080
IEI Timer Faster.exe
```

## 安装包构建

需要 Inno Setup 6：

```cmd
build.bat
```

输出安装包：`dist/IEI_Timer_Faster_Setup.exe`

## 常见问题

**Q: 启动后报错 "端口 5000/5001/5002 均被占用"？**
A: 关闭占用端口的程序后重试，或检查是否有旧实例未关闭。

**Q: 任务列表加载失败？**
A: Playwright Chromium 未正确初始化。检查 `%APPDATA%/gongshi/playwright-browsers/` 目录是否存在。

**Q: 登录后提示"网络异常"？**
A: 检查是否能访问 RDM 服务器 `http://10.111.36.3:2029`。

**Q: 怎么停止程序？**
A: 关闭桌面窗口即可，Flask 后台自动退出。

**Q: 桌面窗口白屏？**
A: 检查系统是否已安装 Edge WebView2 Runtime（Win10 21H2+/Win11 内置）。
