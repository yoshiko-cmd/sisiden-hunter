#!/usr/bin/env bash
# SISIDEN 案件ハンター セットアップ
#
# 使い方: プロジェクトフォルダの中で bash setup.sh を実行するだけ。
# Python環境の準備、必要なライブラリの導入、DB作成、実APIの接続確認まで一度に行う。

set -u

cd "$(dirname "$0")"

echo "============================================================"
echo " SISIDEN 全国自治体案件ハンター セットアップ"
echo "============================================================"
echo ""

# --- 1. Python の確認 ---------------------------------------------------
echo "[1/5] Python を確認しています..."
if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "  Python3 が見つかりませんでした。"
  echo ""
  echo "  【Macの場合】ターミナルで次を実行してください:"
  echo "      xcode-select --install"
  echo "  【Windowsの場合】https://www.python.org/downloads/ からインストールし、"
  echo "      インストール時に 'Add Python to PATH' にチェックを入れてください。"
  exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "      Python $PY_VERSION を使用します"

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo ""
  echo "  Python 3.10 以上が必要です(現在: $PY_VERSION)。"
  echo "  https://www.python.org/downloads/ から新しいバージョンを入れてください。"
  exit 1
fi

# --- 2. 仮想環境の作成 --------------------------------------------------
echo ""
echo "[2/5] 専用のPython環境を作成しています..."
if [ ! -d ".venv" ]; then
  if ! python3 -m venv .venv; then
    echo ""
    echo "  仮想環境の作成に失敗しました。"
    echo "  【Ubuntu/Debianの場合】sudo apt install python3-venv を実行してください。"
    exit 1
  fi
  echo "      .venv を作成しました"
else
  echo "      既存の .venv を使用します"
fi

VENV_PY=".venv/bin/python"
[ -f "$VENV_PY" ] || VENV_PY=".venv/Scripts/python.exe"   # Windows (Git Bash)

# --- 3. ライブラリの導入 ------------------------------------------------
echo ""
echo "[3/5] 必要なライブラリを導入しています(1〜2分かかります)..."
if ! "$VENV_PY" -m pip install --quiet --upgrade pip; then
  echo "      pip の更新に失敗しましたが、続行します"
fi
if ! "$VENV_PY" -m pip install --quiet -r requirements.txt; then
  echo ""
  echo "  ライブラリの導入に失敗しました。"
  echo "  インターネット接続を確認して、もう一度実行してください。"
  exit 1
fi
echo "      完了しました"

# --- 4. データベースの作成 ----------------------------------------------
echo ""
echo "[4/5] データベースを作成しています..."
if ! "$VENV_PY" scripts/init_db.py; then
  echo "  データベースの作成に失敗しました。"
  exit 1
fi

# --- 5. 実APIへの接続確認 -----------------------------------------------
echo ""
echo "[5/5] 官公需情報ポータルへ接続して、実際の案件が取れるか確認します..."
echo ""
"$VENV_PY" scripts/verify_live.py
VERIFY_STATUS=$?

echo ""
echo "============================================================"
if [ $VERIFY_STATUS -eq 0 ]; then
  echo " セットアップ完了。実際の案件を取得できました。"
  echo "============================================================"
  echo ""
  echo " 次にやること:"
  echo ""
  echo "   1. 直近30日の案件を集める"
  echo "      $VENV_PY scripts/collect.py --live --days 30"
  echo ""
  echo "   2. 候補案件の仕様書PDFを読み込む"
  echo "      $VENV_PY scripts/enrich.py --min-score 25"
  echo ""
  echo "   3. Claude Desktop / Claude Code から使えるようにする"
  echo "      設定ファイルに以下を追加してください:"
  echo ""
  echo '      "sisiden-opportunity-mcp": {'
  echo "        \"command\": \"$(pwd)/$VENV_PY\","
  echo "        \"args\": [\"$(pwd)/src/mcp/server.py\"]"
  echo "      }"
else
  echo " セットアップは完了しましたが、案件の取得ができませんでした。"
  echo "============================================================"
  echo ""
  echo " 上に表示されているエラー内容をそのままコピーして送ってください。"
  echo " 原因を特定します。"
fi
echo ""
