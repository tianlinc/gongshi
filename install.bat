@echo off
echo 安装 RDM 工时填报工具依赖...
echo.

echo 正在安装 Python 依赖...
pip install requests pycryptodome beautifulsoup4 pyyaml

echo.
echo ✓ 安装完成！
echo.
echo 使用方法:
echo   1. 测试登录: python test_login.py
echo   2. 填报工时: python rdm_timesheet.py
echo.
pause
