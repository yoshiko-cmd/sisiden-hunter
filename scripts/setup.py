#!/usr/bin/env python3
"""セットアップ(Windows / Mac / Linux 共通)。

標準ライブラリのみで動作する。ライブラリ導入前に実行されるため、
外部パッケージをimportしてはいけない。

Windowsのコマンドプロンプトはバッチファイルの日本語表示が不安定なため、
画面表示はすべてこのPythonスクリプト側で行う(Pythonはコンソールへ
Unicodeを正しく書き出せる)。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"
MIN_PYTHON = (3, 10)


def _reconfigure_stdout() -> None:
    """Windowsコンソールでも日本語が化けないようにする。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def header(text: str) -> None:
    print("=" * 60)
    print(f" {text}")
    print("=" * 60)


def venv_python(venv_dir: Path) -> Path:
    # OSごとの区切り文字で組み立てる(文字列に "/" を混ぜると表示が崩れるため)
    return venv_dir.joinpath(*(("Scripts", "python.exe") if IS_WINDOWS else ("bin", "python")))


def check_python_version() -> bool:
    print(f"[1/5] Python を確認しています... {sys.version_info.major}.{sys.version_info.minor}")
    if sys.version_info < MIN_PYTHON:
        print()
        print(f"  Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 以上が必要です。")
        print("  https://www.python.org/downloads/ から新しいものを入れてください。")
        if IS_WINDOWS:
            print("  ※インストール画面で「Add Python to PATH」に必ずチェックを入れてください。")
        return False
    return True


def create_venv(venv_dir: Path) -> bool:
    print()
    print("[2/5] 専用のPython環境を作成しています...")
    if venv_python(venv_dir).exists():
        print("      既存の環境を使用します")
        return True

    result = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)])
    if result.returncode != 0 or not venv_python(venv_dir).exists():
        print()
        print("  Python環境の作成に失敗しました。")
        if not IS_WINDOWS:
            print("  Ubuntu/Debian の場合: sudo apt install python3-venv を実行してください。")
        return False
    print("      作成しました")
    return True


def install_requirements(py: Path) -> bool:
    print()
    print("[3/5] 必要なライブラリを導入しています(1〜2分かかります)...")
    subprocess.run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    result = subprocess.run(
        [str(py), "-m", "pip", "install", "--quiet", "-r", str(ROOT / "requirements.txt")]
    )
    if result.returncode != 0:
        print()
        print("  ライブラリの導入に失敗しました。")
        print("  インターネット接続を確認して、もう一度実行してください。")
        return False
    print("      完了しました")
    return True


def init_database(py: Path) -> bool:
    print()
    print("[4/5] データベースを作成しています...")
    result = subprocess.run([str(py), str(ROOT / "scripts" / "init_db.py")])
    return result.returncode == 0


def verify_live(py: Path) -> int:
    print()
    print("[5/5] 官公需情報ポータルへ接続して、実際の案件が取れるか確認します...")
    print()
    return subprocess.run([str(py), str(ROOT / "scripts" / "verify_live.py")]).returncode


def print_next_steps(py: Path) -> None:
    py_display = str(py)
    header("セットアップ完了。実際の案件を取得できました")
    print()
    print(" 次にやること:")
    print()
    print("   1. 直近30日の案件を集める")
    print(f"      {py_display} {Path('scripts/collect.py')} --live --days 30")
    print()
    print("   2. 候補案件の仕様書PDFを読み込む")
    print(f"      {py_display} {Path('scripts/enrich.py')} --min-score 25")
    print()
    print("   3. Claude Desktop から使えるようにする")
    print("      設定ファイルの mcpServers に以下を追加してください:")
    print()
    print('      "sisiden-opportunity-mcp": {')
    print(f'        "command": {_json_path(py)},')
    print(f'        "args": [{_json_path(ROOT / "src" / "mcp" / "server.py")}]')
    print("      }")
    print()
    if IS_WINDOWS:
        print("      設定ファイルの場所:")
        print(r"      %APPDATA%\Claude\claude_desktop_config.json")
    else:
        print("      設定ファイルの場所:")
        print("      ~/Library/Application Support/Claude/claude_desktop_config.json")


def _json_path(path: Path) -> str:
    """JSON設定へ貼れる形にする(Windowsのバックスラッシュをエスケープ)。"""
    return '"' + str(path).replace("\\", "\\\\") + '"'


def main() -> int:
    _reconfigure_stdout()
    print()
    header("SISIDEN 全国自治体案件ハンター セットアップ")
    print()

    if not check_python_version():
        return 1

    venv_dir = ROOT / ".venv"
    if not create_venv(venv_dir):
        return 1

    py = venv_python(venv_dir)
    if not install_requirements(py):
        return 1
    if not init_database(py):
        print("  データベースの作成に失敗しました。")
        return 1

    status = verify_live(py)
    print()
    if status == 0:
        print_next_steps(py)
    else:
        header("セットアップは完了しましたが、案件の取得ができませんでした")
        print()
        print(" 上に表示されているエラー内容をそのままコピーして送ってください。")
        print(" 原因を特定します。")
        print()
        print(" よくある原因:")
        print("   ・社内ネットワークが政府サイトへの接続を制限している")
        print("     → 自宅のWi-Fiやスマートフォンのテザリングで試してみてください")
        print("   ・一時的にポータル側がメンテナンス中")
    print()
    return status


if __name__ == "__main__":
    sys.exit(main())
