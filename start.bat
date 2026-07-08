@echo off
title RDM 工时填报系统 v2.0
cls
echo ====================================
echo  RDM 工时填报系统 v2.0
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
    pip install flask flask-cors requests pycryptodome beautifulsoup4
    echo.
)

echo 启动 Web 服务器...
echo.
echo ====================================
echo  服务已启动
echo ====================================
echo.
echo  请在浏览器中访问:
echo    http://localhost:5000
echo.
echo  按 Ctrl+C 停止服务器
echo ====================================
echo.

python app.py
pause
