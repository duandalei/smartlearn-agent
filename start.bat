@echo off
REM ==========================================================================
REM 一键启动脚本（Windows）
REM 先在新窗口启动后端，再在新窗口启动前端。
REM ==========================================================================
setlocal

REM 后端（优先使用 backend\.venv 虚拟环境）
cd /d "%~dp0backend"
if not exist ".env" (
    if exist ".env.example" copy ".env.example" ".env" >nul
)
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
start "SmartLearn Backend" cmd /k "%PY% -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

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