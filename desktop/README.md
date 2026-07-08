# Windows 桌面程序打包

将 RDM 工时填报系统打包为 Windows 桌面应用，双击 exe 即可启动独立的桌面窗口。

## 技术方案

采用 **PyInstaller** 打包（INSPUR-34 架构评审结论）。

**桌面窗口方案：pywebview**
- 使用 Windows 10/11 自带的 **Edge WebView2** 引擎渲染页面
- 独立的原生桌面窗口，不需要 Chrome/Edge 浏览器
- 无需额外安装任何浏览器组件

**为什么是 PyInstaller 而非 Nuitka：**
- Playwright 兼容性：PyInstaller 有成熟打包方案，Nuitka 下 C 编译兼容性问题多
- 构建速度：PyInstaller 2-5 分钟，Nuitka 需要 MSVC + 1-2 小时 C 编译
- 够用原则：内部工具，体积和启动速度可接受
- 反编译不是需求：无敏感业务逻辑需要机器码保护

## 两种"浏览器"说明

| | Playwright Chromium | Edge WebView2 (pywebview) |
|---|---|---|
| **用户可见？** | 不可见 | 可见（桌面窗口） |
| **用途** | 后台爬取 RDM 任务列表 | 显示 Web 界面 |
| **安装方式** | 已预打包进 exe，首次启动秒级复制 | Windows 10/11 自带 |
| **需要联网安装？** | 否（INSPUR-52 预打包） | 否 |

**Playwright Chromium** 是 headless 模式运行的后台爬虫，用于模拟浏览器访问 RDM 抓取任务列表。你永远看不到它。

INSPUR-52 起 Chromium 已预打包进 exe，用户启动后仅需本地文件复制（秒级），无需等待网络下载。

**pywebview 桌面窗口** 是你看到的程序界面，用的是 Windows 系统自带的 WebView2 组件（Edge 的渲染引擎）。

## 文件说明

```
desktop/
├── README.md          # 本文档
├── build.bat          # 一键构建脚本
├── gongshi.spec       # PyInstaller spec 配置（核心）
├── run.py             # 桌面版启动器
├── assets/            # 图标等静态资源（可选）
├── dist/              # 构建产物（gitignore）
│   └── IEI Timer Faster/
│       └── IEI Timer Faster.exe
└── .gitignore
```

## 快速开始

### 前置条件

- Windows 10/11（Win10 需确保安装了 Edge WebView2 Runtime，Win11 自带）
- Python 3.8+
- 已安装项目依赖：`pip install flask flask-cors requests pycryptodome beautifulsoup4 playwright pywebview`

### 一键打包

```cmd
cd desktop
build.bat
```

等待 2-5 分钟，输出在 `dist/IEI Timer Faster/IEI Timer Faster.exe`。

### 手动打包

```cmd
cd desktop
pip install pyinstaller pywebview
pyinstaller --clean --noconfirm gongshi.spec
```

## 工作原理

### 启动流程

1. 双击 `IEI Timer Faster.exe`
2. `run.py` 执行：
   - 初始化用户数据目录 `%APPDATA%/gongshi/`
   - 复制内置缓存文件
   - 复制预打包 Chromium 浏览器到用户目录（INSPUR-52，秒级）
3. 启动 Flask 应用（后台线程，`127.0.0.1:5000`）
4. 弹出独立桌面窗口（pywebview + Edge WebView2）
5. 关闭窗口即退出程序

### 与 Web 版本的区别

| 项目 | Web 版本 (`python app.py`) | 桌面版本 (`IEI Timer Faster.exe`) |
|------|---------------------------|--------------------------|
| 界面 | 系统浏览器 | 独立桌面窗口 (WebView2) |
| 启动方式 | 命令行 | 双击 exe |
| 监听地址 | `0.0.0.0:5000` | `127.0.0.1:5000` |
| debug 模式 | `True` | `False` |
| 工作目录 | 项目根目录 | `%APPDATA%/gongshi/` |
| 缓存目录 | `./cache/` | `%APPDATA%/gongshi/cache/` |

## 分发

将 `dist/IEI Timer Faster/` 整个文件夹复制到目标电脑，双击 `IEI Timer Faster.exe`。

### 注意事项

1. **Windows 防火墙**：首次启动会触发防火墙弹窗，点击"允许访问"
2. **反病毒软件**：部分杀软可能误报 PyInstaller 打包的 exe，添加白名单即可
3. **Chromium 已预打包**（INSPUR-52）：首次启动仅需本地文件复制，无需联网下载
4. **RDM 内网访问**：需要能访问 `http://10.111.36.3:2029`
5. **WebView2 依赖**：Win11 自带；Win10 若缺失会自动提示安装

## 内网镜像加速 Chromium 下载（构建时，INSPUR-51）

INSPUR-52 起 Chromium 已预打包进 exe，**最终用户无需联网下载**。此镜像配置主要用于打包构建机器（`build.bat` 预装 Chromium 时加速下载）。

通过设置 `GONGSHI_MIRROR_HOST` 环境变量，可将下载重定向到内网镜像服务器：

```cmd
set GONGSHI_MIRROR_HOST=http://10.1.1.100:8080
```

或系统环境变量：
```
变量名: GONGSHI_MIRROR_HOST
变量值: http://10.1.1.100:8080
```

### 镜像服务器目录结构

内网镜像服务器需要按以下结构提供 Playwright Chromium 安装包：

```
{host}/playwright-mirror/
├── {browserVersion}/win64/
│   ├── chrome-win64.zip
│   └── chrome-headless-shell-win64.zip
├── builds/ffmpeg/{ffmpegRevision}/
│   └── ffmpeg-win64.zip
└── builds/winldd/{winlddRevision}/
    └── winldd-win64.zip
```

### 镜像文件获取方式

1. 在一台可正常访问公网的 Windows 机器上运行一次 `playwright install chromium`
2. 浏览器缓存位于 `%APPDATA%/gongshi/playwright-browsers/`（或 `%USERPROFILE%/AppData/Local/ms-playwright/`）
3. 将对应文件按上述目录结构上传到内网 HTTP 服务器

### 下载失败处理（构建时）

- `build.bat` 预装失败时，打包继续但 exe 不含预装 Chromium
- 不含预装 Chromium 的 exe 首次启动时回退到下载流程（`/init` 加载页可见）
- 用户可检查镜像服务器状态或网络后重新构建

## 常见问题

**Q: 首次启动卡在加载页很久？**
A: INSPUR-52 起 Chromium 已预打包，启动应秒开。如遇问题，检查 `%APPDATA%/gongshi/run.log` 日志。

**Q: 桌面窗口没有弹出来？**
A: 检查是否缺少 Edge WebView2 Runtime。Win10 用户可下载：https://developer.microsoft.com/microsoft-edge/webview2/

**Q: 启动报错 "Address already in use"？**
A: 端口 5000 被占用。关闭占用进程后重试。

**Q: 任务列表加载失败？**
A: Playwright Chromium 未正确初始化。检查 `%APPDATA%/gongshi/playwright-browsers/` 目录是否存在。

**Q: 登录后提示"网络异常"？**
A: 检查是否能访问 RDM 服务器 `http://10.111.36.3:2029`。
