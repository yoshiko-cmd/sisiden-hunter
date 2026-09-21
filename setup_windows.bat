@echo off
setlocal EnableExtensions
REM SISIDEN opportunity hunter - Windows setup
REM Double-click this file. Japanese messages are printed by scripts\setup.py
REM because batch files cannot display Japanese reliably.

chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo Starting setup...
echo.

if not exist "scripts\setup.py" (
    echo ============================================================
    echo  ERROR: scripts\setup.py was not found.
    echo ============================================================
    echo.
    echo  Please EXTRACT the ZIP file first, then run this file
    echo  from inside the extracted folder.
    echo.
    echo.
    pause
    exit /b 1
)

set "PYCMD="
where py >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD where python >nul 2>&1 && set "PYCMD=python"

if not defined PYCMD (
    echo ============================================================
    echo  Python was not found.
    echo ============================================================
    echo.
    echo  1. Open https://www.python.org/downloads/
    echo  2. Run the installer
    echo  3. IMPORTANT: check "Add Python to PATH"
    echo  4. Close all terminal windows, then run this file again
    echo.
    pause
    exit /b 1
)

%PYCMD% scripts\setup.py

echo.
echo Press any key to close this window.
pause >nul
