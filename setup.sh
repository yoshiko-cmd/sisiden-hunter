#!/usr/bin/env bash
# SISIDEN 案件ハンター セットアップ (Mac / Linux)
# Windowsの場合は setup_windows.bat をダブルクリックしてください。
#
# 実処理は scripts/setup.py にあります(OS共通)。

set -u
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo ""
  echo "  Python3 が見つかりませんでした。"
  echo ""
  echo "  【Macの場合】ターミナルで次を実行してください:"
  echo "      xcode-select --install"
  echo "  【Linuxの場合】sudo apt install python3 python3-venv"
  echo ""
  exit 1
fi

exec python3 scripts/setup.py
