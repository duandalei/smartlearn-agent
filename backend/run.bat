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

REM 首次运行可用 .env.example 生成 .env（不覆盖已有 .env）
if not exist ".env" (
    if exist ".env.example" (
        echo [提示] 未检测到 .env，已由 .env.example 生成，请按需填写真实密钥。
        copy ".env.example" ".env" >nul
    )
)

if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=8000

echo [启动] 后端服务 http://localhost:%PORT%  ^(文档 /docs^)
python -m uvicorn app.main:app --reload --host %HOST% --port %PORT%

endlocal