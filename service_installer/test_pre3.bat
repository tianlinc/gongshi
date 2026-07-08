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

REM ---- 确保从脚本所在目录执行 ----
cd /d "%~dp0"

echo ============================================
echo   IEI Timer Faster 服务版 一键构建
echo   INSPUR-66 - Inno Setup + NSSM 服务注册
echo ============================================
echo.

echo [1/9] 检查 Python...
python --version >nul 2>&1
echo [2/9] 安装 PyInstaller...
echo [3/9] 检查 Playwright...
echo [4/9] 检查 Playwright driver...
echo [5/9] 准备预打包 Chromium 浏览器...
echo [6/9] NSSM 已存在，跳过下载
echo [7/9] 清理构建缓存...
echo [8/9] 构建中，约 2-5 分钟...

echo.
echo ============================================
echo   PyInstaller 构建完成!
echo   产物: dist\IEI Timer Faster Service\
echo ============================================
echo.

echo [9/9] 编译 Inno Setup 安装包...

echo [DEBUG] ISCC at step 9: [%ISCC%]
if defined ISCC (
    echo [OK] ISCC 编译器: %ISCC%
) else (
    echo [X] 未找到 Inno Setup 6 ISCC.exe，跳过安装包编译
    echo.
    echo   如需生成安装包，请安装 Inno Setup 6:
    echo     https://jrsoftware.org/isdl.php
    echo   安装完成后重新运行 build.bat
    echo ============================================
)
