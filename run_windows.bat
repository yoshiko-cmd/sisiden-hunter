@echo off
setlocal EnableExtensions
REM Double-click to collect opportunities and show the top 20.
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setup has not been run yet.
    echo Please double-click setup_windows.bat first.
    echo.
    pause
    exit /b 1
)

set "PY=.venv\Scripts\python.exe"

%PY% scripts\collect.py --live --days 30
echo.
%PY% scripts\rescore.py --show 20

echo.
echo Press any key to close this window.
pause >nul
