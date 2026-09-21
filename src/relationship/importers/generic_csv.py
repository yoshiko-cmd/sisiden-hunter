"""既存営業リスト・メディア/記者リストなど、任意CSVの汎用インポーター。

Eight以外の情報源(手入力Excel/CSV、Googleスプレッドシートのエクスポート等)を
想定する。ヘッダーは common.HEADER_ALIASES で自動マッピングされるが、
一致しない場合は明示的な column_map(実ヘッダー名 -> 標準フィールド名)を渡せる。

媒体名(outlet_name)・ジャンル(genre)・エリア(area)のいずれかの列があれば、
記者・編集者とみなしてmedia_profilesも作成する。
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

_MEDIA_FIELDS = {"outlet_name", "genre", "area", "interest_themes"}


def import_generic_csv(
    conn: sqlite3.Connection,
    file_path: str | Path,
    *,
    source: str = "csv_sales",
    default_org_type: str = "company",
    default_tags: list[str] | None = None,
    column_map: dict[str, str] | None = None,
    is_media: bool = False,
) -> dict[str, Any]:
    path = Path(file_path)
    fieldnames, rows = read_csv_rows(path)
    header_map = build_header_map(fieldnames)
    if column_map:
        header_map.update(column_map)

    if "name" not in header_map.values():
        raise ValueError(
            "氏名列を特定できませんでした。column_map で 実ヘッダー名->'name' を指定してください。"
            f" 検出したヘッダー: {fieldnames}"
        )

    batch_id = start_import_batch(conn, source, path.name)

    new_persons = 0
    matched_persons = 0
    duplicate_candidates = 0
    errors: list[dict[str, Any]] = []

    for i, row in enumerate(rows, start=2):
        mapped = map_row(row, header_map)
        if not mapped.get("name"):
            errors.append({"row": i, "error": "氏名が空のためスキップ"})
            continue
        try:
            result = upsert_person_from_row(
                conn,
                mapped,
                source=source,
                default_org_type=default_org_type,
                import_batch_id=batch_id,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"row": i, "error": str(exc)})
            continue

        person_id = result["person_id"]
        if result["action"] == "matched_email":
            matched_persons += 1
        else:
            new_persons += 1
        duplicate_candidates += len(result["duplicate_candidate_ids"])

        tags = list(default_tags or [])
        if mapped.get("tags"):
            tags.extend(t.strip() for t in mapped["tags"].replace("、", ",").split(",") if t.strip())
        if tags:
            db.add_person_tags(conn, person_id, tags, category="import")

        has_media_field = is_media or any(mapped.get(f) for f in _MEDIA_FIELDS)
        if has_media_field:
            db.upsert_media_profile(
                conn,
                person_id,
                {
                    "outlet_name": mapped.get("outlet_name") or mapped.get("organization_name"),
                    "genre": mapped.get("genre"),
                    "area": mapped.get("area"),
                    "interest_themes": mapped.get("interest_themes"),
                },
            )

    finish_import_batch(
        conn,
        batch_id,
        total_rows=len(rows),
        new_persons=new_persons,
        matched_persons=matched_persons,
        duplicate_candidates_created=duplicate_candidates,
        errors=errors,
        note=f"generic CSV import (source={source})",
    )

    return {
        "batch_id": batch_id,
        "total_rows": len(rows),
        "new_persons": new_persons,
        "matched_persons": matched_persons,
        "duplicate_candidates_created": duplicate_candidates,
        "errors": errors,
    }
