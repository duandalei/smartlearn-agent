@echo off
REM ==========================================================================
REM 一键启动脚本（Windows）
REM 后端与前端优先在 Windows Terminal 中以标签页打开；
REM 未安装 Windows Terminal 时回退为独立 cmd 窗口。
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

REM 2) 启动后端与前端
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
set "BACKEND_CMD=%PY% -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
set "FRONTEND_CMD=npm run dev"

REM 前端依赖检查
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [提示] 未检测到 node_modules，正在安装前端依赖 ...
    pushd "%FRONTEND_DIR%"
    call npm install
    popd
)

REM 已在 Windows Terminal 中运行时，标签页开在当前窗口；
REM 否则使用固定命名的 SmartLearn 窗口（不存在时会自动创建）。
set "WT_WIN=smartlearn"
if defined WT_SESSION set "WT_WIN=0"

where wt.exe >nul 2>&1
if not errorlevel 1 (
    wt -w %WT_WIN% nt -d "%BACKEND_DIR%" --title "SmartLearn Backend" --suppressApplicationTitle cmd /k "%BACKEND_CMD%"
    wt -w %WT_WIN% nt -d "%FRONTEND_DIR%" --title "SmartLearn Frontend" --suppressApplicationTitle cmd /k "%FRONTEND_CMD%"
) else (
    start "SmartLearn Backend" /d "%BACKEND_DIR%" cmd /k "%BACKEND_CMD%"
    start "SmartLearn Frontend" /d "%FRONTEND_DIR%" cmd /k "%FRONTEND_CMD%"
)

echo.
echo 后端与前端已分别打开：
echo   后端: http://localhost:8000/docs
echo   前端: http://localhost:5173
endlocal