@echo off
echo ====================================
echo RDM 工时填报系统 - Web 版
echo ====================================
echo.

echo 检查 Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b
)

echo.
echo 检查依赖...
pip show flask >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖...
    pip install flask flask-cors requests pycryptodome
)

echo.
echo 启动 Web 服务器...
echo.
echo ====================================
echo  请在浏览器中访问:
echo  http://localhost:5000
echo ====================================
echo.
echo 按 Ctrl+C 停止服务器
echo.

python app.py
pause
