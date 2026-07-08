@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

REM ---- 确保从脚本所在目录执行（避免从其他路径运行时找不到 spec/templates 等）----
cd /d "%~dp0"

echo ============================================
echo   IEI Timer Faster Windows 桌面打包工具
echo   INSPUR-36: PyInstaller 打包方案
echo ============================================
echo.

REM ---- Check Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] 未找到 Python，请先安装 Python 3.8+
    echo     下载: https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK] Python %%v
for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)" 2^>^&1') do echo     路径: %%p

REM ---- Install/upgrade PyInstaller ----
echo [1/7] 安装 PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [X] PyInstaller 安装失败，尝试显示详细错误...
    python -m pip install pyinstaller
    exit /b 1
)
echo [OK] PyInstaller 已就绪

REM ---- Check Playwright Python package ----
echo [2/7] 检查 Playwright...
python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo [X] 未安装 Playwright
    echo     请运行: pip install playwright
    exit /b 1
)
for /f "delims=" %%i in ('python -c "import playwright; print(playwright.__file__)"') do set PW_FILE=%%i
echo [OK] Playwright: %PW_FILE%

REM ---- Check Playwright browsers ----
echo [3/7] 检查 Playwright Chromium 浏览器...
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
if errorlevel 1 (
    echo [!] Chromium 未安装，正在安装（首次约 150MB）...
    python -m playwright install chromium
    if errorlevel 1 (
        echo [!] Chromium 安装失败
        echo    桌面版首次启动时将自动安装，或手动运行: playwright install chromium
    ) else (
        echo [OK] Chromium 安装完成
    )
) else (
    echo [OK] Chromium 就绪
)

REM ---- Pre-install Chromium to prebuilt directory (INSPUR-52) ----
echo [4/7] 预置 Chromium 浏览器到打包目录...
set "PREBUILT_DIR=%CD%\playwright-browsers-prebuilt"
set "SYSTEM_PW_DIR=%LOCALAPPDATA%\ms-playwright"

if exist "%PREBUILT_DIR%" (
    echo [OK] 预打包 Chromium 已就绪，跳过下载
) else if exist "%SYSTEM_PW_DIR%" (
    echo     从本地 Playwright 缓存复制 Chromium...
    robocopy "%SYSTEM_PW_DIR%" "%PREBUILT_DIR%" /E /NJH /NJS /NP
    if exist "%PREBUILT_DIR%\chromium-*" (
        echo [OK] Chromium 已从本地缓存复制到 %PREBUILT_DIR%
    ) else (
        echo [!] 复制失败，尝试下载...
        set "PLAYWRIGHT_BROWSERS_PATH=%PREBUILT_DIR%"
        python -m playwright install chromium
        if errorlevel 1 (
            echo [!] Chromium 预置失败，打包将继续但 exe 首次启动时需下载
            if exist "%PREBUILT_DIR%" rmdir /s /q "%PREBUILT_DIR%" 2>nul
        )
    )
) else (
    set "PLAYWRIGHT_BROWSERS_PATH=%PREBUILT_DIR%"
    echo     首次构建，正在下载 Chromium（约 655MB）...
    python -m playwright install chromium
    if errorlevel 1 (
        echo [!] Chromium 预置失败，打包将继续但 exe 首次启动时需下载
        echo     请检查网络连接后重试
        if exist "%PREBUILT_DIR%" rmdir /s /q "%PREBUILT_DIR%" 2>nul
    ) else (
        echo [OK] Chromium 已预置到 %PREBUILT_DIR%
    )
)
echo.
REM ---- Check pywebview (desktop window dependency) ----
echo [5/7] 检查 pywebview（桌面窗口依赖）...
python -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo [!] 未安装 pywebview，正在安装...
    python -m pip install pywebview --quiet 2>nul
    if errorlevel 1 (
        echo [X] pywebview 安装失败，尝试显示详细错误...
        python -m pip install pywebview
        exit /b 1
    )
)
echo [OK] pywebview 已就绪

REM ---- Clean previous build cache (not dist, to avoid locked-file errors) ----
echo [6/7] 清理构建缓存...
if exist "build\gongshi" (
    rmdir /s /q "build\gongshi" 2>nul
    echo [OK] 缓存已清理
) else (
    echo [OK] 无需清理
)

REM ---- Build ----
echo [7/7] 打包中（2-5 分钟）...
echo.
pyinstaller --noconfirm gongshi.spec
if errorlevel 1 (
    echo.
    echo [X] 打包失败！请检查上方错误信息。
    echo    常见原因：
    echo    1. dist\ 目录文件被占用 —— 关闭正在运行的 IEI Timer Faster.exe 后重试
    echo    2. 磁盘空间不足
    exit /b 1
)

echo.
echo ============================================
echo   打包完成！
echo.
echo   输出目录: dist\IEI Timer Faster\
echo   启动程序: dist\IEI Timer Faster\IEI Timer Faster.exe
echo.
echo   分发方式：
echo     将 dist\IEI Timer Faster\ 整个文件夹复制到目标电脑
echo     双击 IEI Timer Faster.exe 即可启动
echo.
echo   首次启动说明：
echo     1. 将 dist\IEI Timer Faster\ 整个文件夹复制到目标电脑
echo     2. 双击 IEI Timer Faster.exe 即可启动
echo     3. 如果弹出 Windows 防火墙提示，请点击"允许"
echo     4. 浏览器组件已预打包，启动后即时可用
echo ============================================
