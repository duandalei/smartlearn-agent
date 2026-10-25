@echo off
REM ==========================================================================
REM 一键启动脚本（Windows）
REM 先在新窗口启动后端，再在新窗口启动前端。
REM ==========================================================================
setlocal

REM 后端（优先使用 backend\.venv 虚拟环境）
cd /d "%~dp0backend"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not exist ".venv\Scripts\python.exe" (
    %PY% --version >nul 2>&1
    if errorlevel 1 (
        where py >nul 2>&1 && py -3 --version >nul 2>&1 && set "PY=py -3"
    )
)

REM 0) 环境自检：缺 .env 时复制模板
%PY% scripts\ensure_dev_env.py
if errorlevel 1 (
    echo [错误] 开发环境自检失败，请检查 backend\.env 与 backend\.env.example
    pause
    exit /b 1
)

REM 1) 首次启动：数据库不存在时自动初始化（建表 + 本地用户）
if not exist "..\data\smartlearn.db" (
    echo [初始化] 未检测到数据库，正在初始化数据库 ...
    %PY% -m app.db.init_db
    if errorlevel 1 (
        echo [错误] 数据库初始化失败，请先安装后端依赖：pip install -r requirements.txt
        pause
        exit /b 1
    )
)

start "SmartLearn Backend" cmd /k "%PY% -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

REM 前端
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo [提示] 未检测到 node_modules，正在安装前端依赖 ...
    call npm install
)
start "SmartLearn Frontend" cmd /k "npm run dev"

echo.
echo 后端窗口与前端窗口已分别打开：
echo   后端: http://localhost:8000/docs
echo   前端: http://localhost:5173
endlocal