@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

REM ---- 确保从脚本所在目录执行 ----
cd /d "%~dp0"

echo ============================================
echo   IEI Timer Faster 轻量版打包工具
echo   INSPUR-62: Lightweight PyInstaller 打包
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

REM ---- Install/upgrade PyInstaller ----
echo [1/6] 安装 PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [X] PyInstaller 安装失败，尝试显示详细错误...
    python -m pip install pyinstaller
    exit /b 1
)
echo [OK] PyInstaller 已就绪

REM ---- Check Playwright Python package ----
echo [2/6] 检查 Playwright...
python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo [X] 未安装 Playwright
    echo     请运行: pip install playwright
    exit /b 1
)
echo [OK] Playwright 已安装

REM ---- Check Playwright driver (bundled Node.js) ----
echo [3/6] 检查 Playwright driver...
python -c "import playwright, os; d=os.path.join(os.path.dirname(playwright.__file__),'driver'); print('OK' if os.path.isdir(d) else 'MISSING')" 2>nul
echo.

REM ---- Clean previous build cache ----
echo [4/6] 清理构建缓存...
if exist "build\lightweight" (
    rmdir /s /q "build\lightweight" 2>nul
    echo [OK] 缓存已清理
) else (
    echo [OK] 无需清理
)

REM ---- Build ----
echo [5/6] 打包中（约 2-5 分钟）...
echo.
pyinstaller --noconfirm lightweight.spec
if errorlevel 1 (
    echo.
    echo [X] 打包失败！请检查上方错误信息。
    echo    常见原因：
    echo    1. dist\ 目录文件被占用 —— 关闭正在运行的 exe 后重试
    echo    2. 磁盘空间不足
    exit /b 1
)

echo.
echo ============================================
echo   PyInstaller 打包完成！
echo   产物: dist\IEI Timer Faster\
echo ============================================
echo.

REM ---- 6. Inno Setup 安装包编译 ----
echo [6/6] 查找 Inno Setup 编译器...

set ISCC=
REM 常见安装路径
for %%d in (
    "C:\Program Files (x86)\Inno Setup 6"
    "C:\Program Files\Inno Setup 6"
    "%ProgramFiles(x86)%\Inno Setup 6"
    "%ProgramFiles%\Inno Setup 6"
    "%LOCALAPPDATA%\Programs\Inno Setup 6"
) do (
    if exist "%%~d\ISCC.exe" (
        set "ISCC=%%~d\ISCC.exe"
    )
)

REM 检查 PATH 中是否可用
if not defined ISCC (
    where iscc >nul 2>&1
    if not errorlevel 1 set "ISCC=iscc"
)

if not defined ISCC (
    echo [!] 未找到 Inno Setup 6 ISCC.exe，跳过安装包编译
    echo.
    echo   如需生成安装包，请安装 Inno Setup 6：
    echo     https://jrsoftware.org/isdl.php
    echo   安装后重新运行 build.bat 即可
    echo.
    echo ============================================
    echo   打包完成（仅 PyInstaller，无安装包）！
    echo.
    echo   分发方式：
    echo     将 dist\IEI Timer Faster\ 整个文件夹复制到目标电脑
    echo     双击 IEI Timer Faster.exe 即可启动
    echo ============================================
    exit /b 0
)

echo [OK] ISCC 编译器: %ISCC%
echo [OK] 正在编译安装包...
echo.

"%ISCC%" /O"dist" /F"IEI_Timer_Faster_Lite_Setup" "installer\setup.iss"
if errorlevel 1 (
    echo.
    echo [X] 安装包编译失败！请检查上方错误信息。
    echo    常见原因：
    echo    1. Inno Setup 版本过旧 —— 需要 6.x
    echo    2. dist\IEI Timer Faster\ 目录不存在 —— 先确认 PyInstaller 打包成功
    exit /b 1
)

echo.
echo ============================================
echo   全流程打包完成！
echo.
echo   PyInstaller 产物: dist\IEI Timer Faster\
echo   安装包:           dist\IEI_Timer_Faster_Lite_Setup.exe
echo.
echo   分发方式（二选一）：
echo     绿色版: 将 dist\IEI Timer Faster\ 文件夹复制到目标电脑
echo     安装版: 将 dist\IEI_Timer_Faster_Lite_Setup.exe 发给用户安装
echo.
echo   首次启动说明：
echo     1. 双击 exe 后自动下载 Chromium（约 150MB，仅首次）
echo     2. 下载完成后自动打开系统浏览器
echo     3. 遇到防火墙提示请点"允许"
echo ============================================
