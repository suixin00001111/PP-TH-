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

"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

"%PYTHON%" web.py --host 127.0.0.1 --port 8080
pause
