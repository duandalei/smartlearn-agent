@echo off
REM ==========================================================================
REM SmartLearn 一键环境配置（Windows）
REM 用法：双击本文件，或在项目根目录执行 setup.bat
REM 完成后双击 start.bat 启动项目
REM ==========================================================================
setlocal
cd /d "%~dp0"

set "PY=python"
if exist "backend\.venv\Scripts\python.exe" set "PY=backend\.venv\Scripts\python.exe"
if not exist "backend\.venv\Scripts\python.exe" (
    %PY% --version >nul 2>&1
    if errorlevel 1 (
        where py >nul 2>&1 && py -3 --version >nul 2>&1 && set "PY=py -3"
    )
)

%PY% --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python。请安装 Python 3.10+ 并勾选 "Add Python to PATH"。
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

%PY% scripts\setup_env.py %*
if errorlevel 1 (
    echo.
    echo [失败] 环境配置未完成，请查看上方错误信息并按提示处理。
    pause
    exit /b 1
)

echo.
echo [完成] 现在双击 start.bat 启动项目。
endlocal
