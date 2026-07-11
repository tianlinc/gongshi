@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

REM ---- 预先检测 Inno Setup 6 ISCC.exe ----
set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    where iscc >nul 2>&1
    if not errorlevel 1 set "ISCC=iscc"
)

echo [DBG] %%LOCALAPPDATA%%=%LOCALAPPDATA%
echo [DBG] ISCC pre-detect: [%ISCC%]
echo [DBG] cd before: [%CD%]
REM ---- 确保从脚本所在目录执行 ----
cd /d "%~dp0"

echo ============================================
echo   IEI Timer Faster 桌面版 一键构建
echo   INSPUR-74 - pywebview + WebView2 桌面应用
echo ============================================
echo.

REM ============================================================
REM  步骤 1: 检查 Python
REM ============================================================
echo [1/6] 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] 未找到 Python，请先安装 Python 3.8+
    echo     下载: https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [OK] Python %%v

REM ============================================================
REM  步骤 2: 安装/升级 PyInstaller
REM ============================================================
echo [2/6] 安装 PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [X] PyInstaller 安装失败，查看详细错误...
    python -m pip install pyinstaller
    exit /b 1
)
echo [OK] PyInstaller 已就绪

REM ============================================================
REM  步骤 3: 检查 pywebview
REM ============================================================
echo [3/6] 检查 pywebview...
python -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo [!] 未安装 pywebview，正在安装...
    python -m pip install pywebview --quiet
    if errorlevel 1 (
        echo [X] pywebview 安装失败
        echo     请手动执行: pip install pywebview
        exit /b 1
    )
)
echo [OK] pywebview 已就绪


REM ---- 停止旧的运行实例（防止 PyInstaller 因文件被占用而失败）----
taskkill /f /im "IEI Timer Faster.exe" >nul 2>&1

REM ============================================================
REM  步骤 4: 清理构建缓存和旧产物
REM ============================================================
echo [4/6] 清理构建缓存和旧产物...
if exist "dist\IEI Timer Faster" (
    rmdir /s /q "dist\IEI Timer Faster" 2>nul
    echo [OK] 已清理旧 dist 产物
)
if exist "build\service" (
    rmdir /s /q "build\service" 2>nul
    echo [OK] 已清理缓存
) else (
    echo [OK] 无需清理
)

REM ============================================================
REM  步骤 5: PyInstaller 构建
REM ============================================================
echo [5/6] 构建中，约 2-5 分钟...
echo.
python -m PyInstaller --noconfirm service.spec
if errorlevel 1 (
    echo.
    echo [X] 构建失败，请检查上方错误信息
    echo   常见原因:
    echo    1. dist\ 目录文件被占用 -- 关闭所有运行中的 exe 后重试
    echo    2. 磁盘空间不足
    exit /b 1
)

echo.
echo ============================================
echo   PyInstaller 构建完成!
echo   产物: dist\IEI Timer Faster\
echo ============================================
echo.

REM 清理 onedir 流水线产生的冗余 standalone exe（与 onedir 目录内的 exe 重复）
if exist "dist\IEI Timer Faster.exe" (
    del /q "dist\IEI Timer Faster.exe" >nul 2>&1
)

REM ============================================================
REM  步骤 6: Inno Setup 安装包编译（可选）
REM ============================================================
echo [6/6] 编译 Inno Setup 安装包...

echo [DBG9] ISCC at step 9: [%ISCC%]
if not "%ISCC%"=="" goto :have_iscc

echo [X] 未找到 Inno Setup 6 ISCC.exe，跳过安装包编译
echo.
echo   当前构建产出了桌面程序，但未生成引导式安装包。
echo.
echo   dist\IEI Timer Faster\IEI Timer Faster.exe  -- 桌面程序 (双击即启动)
echo   dist\IEI_Timer_Faster_Setup.exe              -- (X) 未生成
echo.
echo   如需生成安装包，请安装 Inno Setup 6:
echo     https://jrsoftware.org/isdl.php
echo   安装完成后重新运行 build.bat
echo ============================================
exit /b 0

:have_iscc
echo [OK] ISCC 编译器: %ISCC%

REM 检查中文语言文件（静默安装 Inno Setup 可能缺 ChineseSimplified.isl）
for %%f in ("%ISCC%") do set "ISCC_DIR=%%~dpf"
if not exist "!ISCC_DIR!Languages" mkdir "!ISCC_DIR!Languages"
if not exist "!ISCC_DIR!Languages\ChineseSimplified.isl" (
    echo [X] 中文语言文件缺失，正在下载...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl' -OutFile '!ISCC_DIR!Languages\ChineseSimplified.isl' -UseBasicParsing" 2>nul
    if not exist "!ISCC_DIR!Languages\ChineseSimplified.isl" (
        echo [X] 中文语言文件下载失败，请确保网络连通后重试
        echo     或手动下载: https://raw.githubusercontent.com/jrsoftware/issrc/main/Files/Languages/ChineseSimplified.isl
        echo     放到 !ISCC_DIR!Languages\
        exit /b 1
    )
    echo [OK] 中文语言文件下载完成
)

echo [OK] 正在编译安装包...
echo.

REM 从 VERSION 文件读取版本号
set VERSION=
for /f "usebackq delims=" %%v in ("..\VERSION") do set "VERSION=%%v"
echo [DBG] VERSION=%VERSION%
if "%VERSION%"=="" set "VERSION=unknown"

"%ISCC%" /O"dist" /F"IEI_Timer_Faster_Setup_v%VERSION%" "installer\setup.iss"
if errorlevel 1 (
    echo.
    echo [X] 安装包编译失败，请检查上方错误信息
    echo   常见原因:
    echo    1. Inno Setup 版本过低 -- 需要 6.x
    echo    2. dist\IEI Timer Faster\ 目录不存在 -- 请确认 PyInstaller 构建成功
    exit /b 1
)

REM 清理 PyInstaller onedir 中间产物（已打包进安装程序）
echo.
echo [OK] 清理构建中间产物...
rmdir /s /q "dist\IEI Timer Faster" 2>nul
echo [OK] 中间产物已清理

echo.
echo ============================================
echo   全流程构建完成!
echo.
echo   安装包: dist\IEI_Timer_Faster_Setup_v%VERSION%.exe
echo.
echo   安装包使用说明:
echo     1. 运行 IEI_Timer_Faster_Setup.exe
echo     2. 选择安装路径 (默认: %%LOCALAPPDATA%%\IEI Timer Faster)
echo     3. 安装后自动创建桌面快捷方式
echo     4. 双击桌面快捷方式即可在独立窗口中访问
echo        (无需系统浏览器，使用系统自带的 Edge WebView2)
echo.
echo   卸载说明:
echo     控制面板 - 程序和功能 - IEI Timer Faster
echo     或: 开始菜单 - IEI Timer Faster - 卸载 IEI Timer Faster
echo     卸载时自动清理应用目录
echo ============================================
