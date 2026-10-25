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

REM 环境自检：缺 .env 时复制模板；JWT_SECRET 仍为占位值时自动生成随机值
python scripts\ensure_dev_env.py
if errorlevel 1 exit /b 1

REM 首次启动：数据库不存在时写入演示种子数据
if not exist "..\data\smartlearn.db" (
    echo [初始化] 未检测到数据库，正在写入演示种子数据 ...
    python -m app.db.init_db
    if errorlevel 1 exit /b 1
)

if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8000

echo [启动] 后端服务 http://localhost:%PORT%  ^(文档 /docs^)
python -m uvicorn app.main:app --reload --host %HOST% --port %PORT%

endlocal