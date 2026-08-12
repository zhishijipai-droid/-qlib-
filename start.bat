@echo off
chcp 65001 >nul
cd /d %~dp0

echo =============================================
echo   QUANT DESK — 量化策略面板 一键启动
echo =============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 安装依赖 (首次运行)
echo [1/3] 检查依赖...
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [警告] 部分依赖安装失败，尝试继续...
)

:: 检查数据库
echo [2/3] 检查数据...
if not exist "bt_panel\server\bt_panel.db" (
    echo [信息] 首次运行，正在初始化数据库...
    python -c "from bt_panel.server.db import init_db, seed_data; init_db(); seed_data()" 2>nul
)

:: 启动服务
echo [3/3] 启动服务...
echo.
echo   面板地址: http://localhost:8100
echo   按 Ctrl+C 停止服务
echo.
start http://localhost:8100

cd bt_panel\server
python -m uvicorn main:app --host 0.0.0.0 --port 8100 --reload

pause
