"""Eightエクスポートcsvのインポート(Eight APIは前提としない)。

想定項目: 氏名/会社/部署/役職/メール/電話/住所/名刺交換日/Eightタグ/メモ

1行につき:
  1. 会社名から組織を解決(無ければ作成)
  2. 人物をdedup付きで登録(メール一致なら統合、それ以外の一致は重複候補として記録)
  3. Eightタグをperson_tagsへ登録(category='eight_tag')
  4. 「名刺交換」のInteractionを1件記録(名刺交換日が資産として残る)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.relationship.database import db
from src.relationship.importers.common import (
    build_header_map,
    finish_import_batch,
    map_row,
    read_csv_rows,
    start_import_batch,
    upsert_person_from_row,
)

_TAG_SPLIT_CHARS = ["、", ",", "/", "・", ";"]


def _split_tags(raw: str) -> list[str]:
    value = raw
    for ch in _TAG_SPLIT_CHARS:
        value = value.replace(ch, ",")
    return [t.strip() for t in value.split(",") if t.strip()]


def import_eight_csv(conn: sqlite3.Connection, file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    fieldnames, rows = read_csv_rows(path)
    header_map = build_header_map(fieldnames)

    if "name" not in header_map.values():
        raise ValueError(
            "氏名列が見つかりませんでした。CSVヘッダーに「氏名」等が含まれているか確認してください。"
            f" 検出したヘッダー: {fieldnames}"
        )

    batch_id = start_import_batch(conn, "eight", path.name)

    new_persons = 0
    matched_persons = 0
    duplicate_candidates = 0
    errors: list[dict[str, Any]] = []

    for i, row in enumerate(rows, start=2):  # 2行目からがデータ(1行目はヘッダー)
        mapped = map_row(row, header_map)
        if not mapped.get("name"):
            errors.append({"row": i, "error": "氏名が空のためスキップ"})
            continue
        try:
            result = upsert_person_from_row(
                conn,
                mapped,
                source="eight",
                default_org_type="company",
                import_batch_id=batch_id,
            )
        except Exception as exc:  # noqa: BLE001 - インポートは1行失敗しても継続する
            errors.append({"row": i, "error": str(exc)})
            continue

        person_id = result["person_id"]
        if result["action"] == "matched_email":
            matched_persons += 1
        else:
            new_persons += 1
        duplicate_candidates += len(result["duplicate_candidate_ids"])

        if mapped.get("tags"):
            db.add_person_tags(conn, person_id, _split_tags(mapped["tags"]), category="eight_tag")

        if mapped.get("first_met_at"):
            try:
                db.log_interaction(
                    conn,
                    {
                        "person_id": person_id,
                        "date": mapped["first_met_at"],
                        "channel": "business_card",
                        "direction": "inbound",
                        "subject": "名刺交換(Eight)",
                        "summary": mapped.get("notes"),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                errors.append({"row": i, "error": f"Interaction記録に失敗: {exc}"})

    finish_import_batch(
        conn,
        batch_id,
        total_rows=len(rows),
        new_persons=new_persons,
        matched_persons=matched_persons,
        duplicate_candidates_created=duplicate_candidates,
        errors=errors,
        note="Eight CSV import",
    )

    return {
        "batch_id": batch_id,
        "total_rows": len(rows),
        "new_persons": new_persons,
        "matched_persons": matched_persons,
        "duplicate_candidates_created": duplicate_candidates,
        "errors": errors,
    }
