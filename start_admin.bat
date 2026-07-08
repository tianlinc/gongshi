@echo off
title License 签发管理端
cls
echo ====================================
echo  License 签发管理端
echo ====================================
echo.

echo 正在检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo 正在检查依赖...
pip show flask >nul 2>&1
if errorlevel 1 (
    echo 首次运行，正在安装依赖...
    pip install flask flask-cors
    echo.
)

echo 启动管理端服务器...
echo.
echo ====================================
echo  管理端已启动
echo ====================================
echo.
echo  请在浏览器中访问:
echo    http://localhost:5001
echo.
echo  按 Ctrl+C 停止服务器
echo ====================================
echo.

python admin_server.py
pause
