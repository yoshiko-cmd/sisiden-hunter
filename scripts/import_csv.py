#!/usr/bin/env python3
"""既存営業リスト・メディア/記者リスト等、任意CSVをRelationship OSへ取り込む。

使い方:
    # 既存営業リスト
    python scripts/import_csv.py --file sales_list.csv --source csv_sales --tags "見込み顧客"

    # メディア・記者リスト(is_mediaを立てるとmedia_profileも作成される)
    python scripts/import_csv.py --file press_list.csv --source csv_media --tags "記者" --media

    # ヘッダーが自動認識されない場合は明示マッピング(実ヘッダー名 -> 標準フィールド名)
    python scripts/import_csv.py --file list.csv --source csv_sales \\
        --mapping '{"担当者":"name","勤務先":"organization_name"}'
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.relationship.database.db import DEFAULT_DB_PATH, get_connection
from src.relationship.importers.generic_csv import import_generic_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="汎用CSVインポート(既存営業リスト/メディアリスト等)")
    parser.add_argument("--file", required=True, help="CSVファイルのパス")
    parser.add_argument("--source", default="csv_sales", help="データ源の識別子(例: csv_sales, csv_media)")
    parser.add_argument("--org-type", default="company", help="組織が未登録の場合に作成する種別(company/municipality/school/university/media/ngo/association/other)")
    parser.add_argument("--tags", default="", help="全行に付与するタグ(カンマ区切り)")
    parser.add_argument("--media", action="store_true", help="記者・編集者リストとして取り込む(media_profileを作成)")
    parser.add_argument("--mapping", default=None, help='実ヘッダー名->標準フィールド名 のJSONマッピング(自動認識できない場合)')
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="DBファイルパス(省略時はデフォルト)")
    args = parser.parse_args()

    default_tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    column_map = json.loads(args.mapping) if args.mapping else None

    conn = get_connection(args.db)
    try:
        result = import_generic_csv(
            conn,
            args.file,
            source=args.source,
            default_org_type=args.org_type,
            default_tags=default_tags,
            column_map=column_map,
            is_media=args.media,
        )
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
