@echo off
REM ==========================================================================
REM 后端启动脚本（Windows）
REM 用法：双击 或 在命令行执行 run.bat
REM ==========================================================================
setlocal

REM 切换到脚本所在目录（backend\）
cd /d "%~dp0"

REM 若存在虚拟环境则自动激活
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

REM 解释器优先级：venv -> py -3 -> python
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not exist ".venv\Scripts\python.exe" (
    %PY% --version >nul 2>&1
    if errorlevel 1 (
        where py >nul 2>&1 && py -3 --version >nul 2>&1 && set "PY=py -3"
    )
)

REM 环境自检：缺 .env 时复制模板
%PY% scripts\ensure_dev_env.py
if errorlevel 1 exit /b 1

REM 首次启动：数据库不存在时初始化（建表 + 本地用户）
if not exist "..\data\smartlearn.db" (
    echo [初始化] 未检测到数据库，正在初始化数据库 ...
    %PY% -m app.db.init_db
    if errorlevel 1 exit /b 1
)

if "%HOST%"=="" set HOST=127.0.0.1
if "%PORT%"=="" set PORT=8000

echo [启动] 后端服务 http://localhost:%PORT%  ^(文档 /docs^)
%PY% -m uvicorn app.main:app --reload --host %HOST% --port %PORT%

endlocal