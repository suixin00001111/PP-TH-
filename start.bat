@echo off
setlocal
cd /d "%~dp0"

set "PYTHON="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0.venv\bin\python.exe" set "PYTHON=%~dp0.venv\bin\python.exe"
if not defined PYTHON (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python was not found. Create .venv or install Python first.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Creating virtualenv...
    python -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo Failed to create .venv
        pause
        exit /b 1
    )
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
)

"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

if not exist "%~dp0.env" if exist "%~dp0.env.example" copy /Y "%~dp0.env.example" "%~dp0.env" >nul

REM Avoid curl 77 when the project path contains non-ASCII (e.g. Chinese username).
"%PYTHON%" -c "from paypal.ssl_env import ensure_ssl_cert_env; print(ensure_ssl_cert_env())" 2>nul

echo Starting Web UI at http://127.0.0.1:8080
"%PYTHON%" web.py --host 127.0.0.1 --port 8080
pause
