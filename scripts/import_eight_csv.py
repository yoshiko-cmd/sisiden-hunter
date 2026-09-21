#!/usr/bin/env python3
"""EightエクスポートCSVをRelationship OSへ取り込む。

使い方:
    python scripts/import_eight_csv.py --file path/to/eight_export.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.relationship.database.db import DEFAULT_DB_PATH, get_connection
from src.relationship.importers.eight_csv import import_eight_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Eight CSVインポート")
    parser.add_argument("--file", required=True, help="Eightからエクスポートしたcsvファイルのパス")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="DBファイルパス(省略時はデフォルト)")
    args = parser.parse_args()

    conn = get_connection(args.db)
    try:
        result = import_eight_csv(conn, args.file)
    finally:
        conn.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(
        f"\n取込完了: 全{result['total_rows']}行 / 新規{result['new_persons']}人 / "
        f"既存統合{result['matched_persons']}人 / 重複候補{result['duplicate_candidates_created']}件"
    )
    if result["errors"]:
        print(f"警告: {len(result['errors'])}件のエラーがありました(詳細は上記JSON参照)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
