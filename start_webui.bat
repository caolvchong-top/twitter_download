@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Twitter / X Downloader WebUI
cd /d "%~dp0"

echo ==================================================
echo   Twitter / X 下载器 WebUI 启动器
echo ==================================================
echo.

:: 1. 自动查找可用的 Python (>= 3.10)
set "PY_CMD="
set "PY_ARGS="

for %%P in (
    "%~dp0.venv\Scripts\python.exe"
    "%~dp0venv\Scripts\python.exe"
    "%~dp0.conda\python.exe"
) do (
    if not defined PY_CMD if exist "%%~P" (
        "%%~P" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PY_CMD=%%~P"
    )
)

if not defined PY_CMD (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "PY_CMD=python"
    )
)

if not defined PY_CMD (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if !errorlevel! equ 0 (
            set "PY_CMD=py"
            set "PY_ARGS=-3"
        )
    )
)

if not defined PY_CMD (
    echo [错误] 未检测到 Python 3.10 及以上版本！
    echo.
    echo 请先安装 Python 3.10+：https://www.python.org/downloads/
    echo 安装时请务必勾选底部 "Add python.exe to PATH"。
    echo.
    pause
    exit /b 1
)

echo [环境] 使用 Python: !PY_CMD! !PY_ARGS!
"!PY_CMD!" !PY_ARGS! --version

:: 2. 检查核心依赖，缺少时自动安装
"!PY_CMD!" !PY_ARGS! -c "import httpx, socksio, x_client_transaction, fastapi, uvicorn" >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo [提示] 检测到缺少运行依赖，正在自动安装 requirements.txt ...
    "!PY_CMD!" !PY_ARGS! -m pip install -r "%~dp0requirements.txt"
    if !errorlevel! neq 0 (
        echo.
        echo [错误] 依赖安装失败！请检查网络或手动执行：
        echo        pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

:: 3. 启动 WebUI（默认仅本机 http://127.0.0.1:7860 并自动打开浏览器）
echo.
echo [启动] 正在启动 WebUI，关闭本窗口或按 Ctrl+C 可停止服务...
echo.
"!PY_CMD!" !PY_ARGS! "%~dp0webui.py" %*

if !errorlevel! neq 0 (
    echo.
    echo [提示] WebUI 异常退出（错误码 !errorlevel!），如提示端口被占用可尝试：
    echo        start_webui.bat --port 8080
    echo.
    pause
)
endlocal
