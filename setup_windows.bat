@echo off
REM SISIDEN opportunity hunter - Windows setup
REM Double-click this file to set up. All Japanese messages are printed by
REM scripts\setup.py, because batch files cannot show Japanese reliably.

chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo Starting setup... / セットアップを開始します
echo.

REM Prefer the py launcher (installed by python.org), fall back to python.
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 scripts\setup.py
    goto :done
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
    python scripts\setup.py
    goto :done
)

echo.
echo ============================================================
echo  Python was not found. / Python が見つかりませんでした
echo ============================================================
echo.
echo  1. Open https://www.python.org/downloads/
echo  2. Download and run the installer
echo  3. IMPORTANT: check "Add Python to PATH" on the first screen
echo  4. Restart this file
echo.
echo  Python をインストールしてから、もう一度このファイルを
echo  ダブルクリックしてください。
echo  インストール画面の "Add Python to PATH" に必ずチェックを入れてください。
echo.

:done
echo.
echo Press any key to close this window. / 何かキーを押すと閉じます
pause >nul
