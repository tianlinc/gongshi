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
echo   IEI Timer Faster 服务版 一键构建
echo   INSPUR-66 - Inno Setup + NSSM 服务注册
echo ============================================
echo.

REM ============================================================
REM  步骤 1: 检查 Python
REM ============================================================
echo [1/9] 检查 Python...
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
echo [2/9] 安装 PyInstaller...
python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [X] PyInstaller 安装失败，查看详细错误...
    python -m pip install pyinstaller
    exit /b 1
)
echo [OK] PyInstaller 已就绪

REM ============================================================
REM  步骤 3: 检查 Playwright Python 包
REM ============================================================
echo [3/9] 检查 Playwright...
python -c "import playwright" >nul 2>&1
if errorlevel 1 (
    echo [X] 未安装 Playwright
    echo     安装命令: pip install playwright
    exit /b 1
)
echo [OK] Playwright 已安装

REM ============================================================
REM  步骤 4: 检查 Playwright driver
REM ============================================================
echo [4/9] 检查 Playwright driver...
python -c "import playwright, os; d=os.path.join(os.path.dirname(playwright.__file__),'driver'); print('OK' if os.path.isdir(d) else 'MISSING')" 2>nul
echo.

REM ============================================================
REM  步骤 5: 准备预打包 Chromium 浏览器 (INSPUR-52)
REM ============================================================
echo [5/9] 准备预打包 Chromium 浏览器...

set "PREBUILT_DIR=%CD%\playwright-browsers-prebuilt"
set "DESKTOP_PREBUILT=%CD%\..\desktop\playwright-browsers-prebuilt"
set "SYSTEM_PW_DIR=%LOCALAPPDATA%\ms-playwright"

if exist "%PREBUILT_DIR%" (
    echo [OK] 预打包 Chromium 已就绪
    goto :skip_prebuilt
)

REM 方案1: 从 desktop/ 的预打包目录复制
if exist "%DESKTOP_PREBUILT%" (
    echo     从 desktop/playwright-browsers-prebuilt/ 复制 Chromium...
    robocopy "%DESKTOP_PREBUILT%" "%PREBUILT_DIR%" /E /NJH /NJS /NP >nul
    if exist "%PREBUILT_DIR%\chromium-*" (
        echo [OK] 已从 desktop/ 复制
        goto :skip_prebuilt
    )
    echo [X] 复制失败，尝试其他方式...
    rmdir /s /q "%PREBUILT_DIR%" 2>nul
)

REM 方案2: 从系统 Playwright 缓存复制
if exist "%SYSTEM_PW_DIR%" (
    echo     从本地 Playwright 缓存复制 Chromium...
    robocopy "%SYSTEM_PW_DIR%" "%PREBUILT_DIR%" /E /NJH /NJS /NP >nul
    if exist "%PREBUILT_DIR%\chromium-*" (
        echo [OK] 已从系统缓存复制
        goto :skip_prebuilt
    )
    echo [X] 复制失败，尝试下载...
    rmdir /s /q "%PREBUILT_DIR%" 2>nul
)

REM 方案3: 下载 Chromium 到预打包目录
echo     首次构建，正在下载 Chromium (约 655MB)...
set "PLAYWRIGHT_BROWSERS_PATH=%PREBUILT_DIR%"
python -m playwright install chromium
if errorlevel 1 (
    echo [X] Chromium 下载失败
    echo    构建将继续，但产物不含预打包 Chromium (首次启动需联网下载约150MB)
    if exist "%PREBUILT_DIR%" rmdir /s /q "%PREBUILT_DIR%" 2>nul
) else (
    echo [OK] Chromium 已预置
)

:skip_prebuilt
echo.

REM ============================================================
REM  步骤 6: 下载 NSSM (如需)
REM ============================================================
if exist "bin\nssm.exe" (
    echo [6/9] NSSM 已存在，跳过下载
    goto :skip_nssm
)

echo [6/9] 下载 NSSM 2.24...
if not exist "bin" mkdir "bin"

echo     正在从 nssm.cc 下载...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile 'bin\nssm.zip'"
if errorlevel 1 (
    echo [X] NSSM 下载失败，请检查网络连接
    echo     手动下载: https://nssm.cc/release/nssm-2.24.zip
    echo     解压后将 nssm-2.24\win64\nssm.exe 放到 bin\ 目录
    exit /b 1
)

echo     正在解压...
powershell -Command "Expand-Archive -Path 'bin\nssm.zip' -DestinationPath 'bin\nssm-tmp' -Force"
if errorlevel 1 (
    echo [X] NSSM 解压失败
    exit /b 1
)

copy /Y "bin\nssm-tmp\nssm-2.24\win64\nssm.exe" "bin\nssm.exe" >nul
if errorlevel 1 (
    echo [X] NSSM 提取失败，请手动解压
    exit /b 1
)

rmdir /s /q "bin\nssm-tmp" 2>nul
del "bin\nssm.zip" 2>nul
echo [OK] NSSM 下载完成

:skip_nssm

REM ---- 停止旧的运行实例（防止 PyInstaller 因文件被占用而失败）----
taskkill /f /im "IEI Timer Faster Service.exe" >nul 2>&1

REM ============================================================
REM  步骤 7: 清理构建缓存
REM ============================================================
echo [7/9] 清理构建缓存...
if exist "build\service" (
    rmdir /s /q "build\service" 2>nul
    echo [OK] 已清理缓存
) else (
    echo [OK] 无需清理
)

REM ============================================================
REM  步骤 8: PyInstaller 构建
REM ============================================================
echo [8/9] 构建中，约 2-5 分钟...
echo.
pyinstaller --noconfirm service.spec
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
echo   产物: dist\IEI Timer Faster Service\
echo ============================================
echo.

REM 清理 onedir 流水线产生的冗余 standalone exe（与 onedir 目录内的 exe 重复）
if exist "dist\IEI Timer Faster Service.exe" (
    del /q "dist\IEI Timer Faster Service.exe" >nul 2>&1
)

REM ============================================================
REM  步骤 9: Inno Setup 安装包编译
REM ============================================================
echo [9/9] 编译 Inno Setup 安装包...

echo [DBG9] ISCC at step 9: [%ISCC%]
if not "%ISCC%"=="" goto :have_iscc

echo [X] 未找到 Inno Setup 6 ISCC.exe，跳过安装包编译
echo.
echo   当前构建产出了服务程序，但未生成引导式安装包。
echo.
echo   dist\IEI Timer Faster Service\IEI Timer Faster Service.exe  -- 服务程序 (双击即启动)
echo   dist\IEI_Timer_Faster_Service_Setup.exe                    -- (X) 未生成
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

"%ISCC%" /O"dist" /F"IEI_Timer_Faster_Service_Setup" "installer\setup.iss"
if errorlevel 1 (
    echo.
    echo [X] 安装包编译失败，请检查上方错误信息
    echo   常见原因:
    echo    1. Inno Setup 版本过低 -- 需要 6.x
    echo    2. dist\IEI Timer Faster Service\ 目录不存在 -- 请确认 PyInstaller 构建成功
    echo    3. bin\nssm.exe 不存在 -- 请确认步骤 6 下载成功
    exit /b 1
)

echo.
echo ============================================
echo   全流程构建完成!
echo.
echo   PyInstaller 产物: dist\IEI Timer Faster Service\
echo   安装包:           dist\IEI_Timer_Faster_Service_Setup.exe
echo.
echo   安装包使用说明:
echo     1. 运行 IEI_Timer_Faster_Service_Setup.exe
echo     2. 选择安装路径 (默认: %%LOCALAPPDATA%%\IEI Timer Faster)
echo     3. 安装过程自动注册并启动 Windows 服务
echo        (服务注册需要管理员权限, 安装时会弹 UAC 提权确认)
echo     4. 安装完成后浏览器访问 http://localhost:5000
echo.
echo   卸载说明:
echo     控制面板 - 程序和功能 - IEI Timer Faster (服务版)
echo     或: 开始菜单 - IEI Timer Faster - 卸载 IEI Timer Faster
echo     卸载时自动停止并删除 Windows 服务
echo ============================================
