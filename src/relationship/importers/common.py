"""CSVインポート共通処理。

Eight CSV / 既存営業リスト / メディア・記者リストなど、複数のソースから
同じ人物中心DB(persons)へ取り込むための共通ロジックをここに集約する。
ヘッダー名の表記ゆれを吸収し、db.upsert_person()の重複判定に委ねる。
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from src.relationship.database import db

# 各カラムに対応しうるヘッダー名のゆれ(小文字化して比較)
HEADER_ALIASES: dict[str, list[str]] = {
    "name": ["氏名", "名前", "name", "full_name", "お名前"],
    "name_kana": ["氏名カナ", "フリガナ", "ふりがな", "name_kana", "kana"],
    "organization_name": ["会社", "会社名", "組織", "組織名", "所属", "company", "organization", "勤務先"],
    "department": ["部署", "部署名", "department", "所属部署"],
    "job_title": ["役職", "肩書き", "肩書", "title", "job_title", "position"],
    "email": ["メール", "メールアドレス", "eメール", "email", "mail", "e-mail"],
    "email_secondary": ["メール2", "メールアドレス2", "email2", "sub_email"],
    "phone": ["電話", "電話番号", "tel", "phone", "携帯", "携帯電話"],
    "location": ["住所", "所在地", "address", "location", "エリア"],
    "first_met_at": ["名刺交換日", "出会った日", "初回接点日", "first_met_at", "交換日"],
    "tags": ["タグ", "eightタグ", "eight_tag", "eightタグ(複数可)", "tags"],
    "notes": ["メモ", "備考", "note", "notes", "memo"],
    "outlet_name": ["媒体", "媒体名", "outlet", "outlet_name", "メディア名"],
    "genre": ["担当ジャンル", "ジャンル", "genre"],
    "area": ["担当エリア", "genre_area", "area"],
    "interest_themes": ["興味テーマ", "関心テーマ", "interest_themes", "themes"],
}


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower()


def build_header_map(fieldnames: list[str]) -> dict[str, str]:
    """CSVの実際のヘッダー名 -> 標準フィールド名 のマップを作る。"""
    result: dict[str, str] = {}
    normalized = {_normalize_header(h): h for h in fieldnames}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            key = _normalize_header(alias)
            if key in normalized:
                result[normalized[key]] = canonical
                break
    return result


def read_csv_rows(file_path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    """BOM付きUTF-8/CP932(Shift-JIS)を試してCSVを読む(Eight/日本語Excel由来を想定)。"""
    path = Path(file_path)
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp932", "utf-8"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)
            return fieldnames, rows
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
    raise ValueError(f"CSVの文字コードを判定できませんでした: {file_path}") from last_error


def map_row(row: dict[str, str], header_map: dict[str, str]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for raw_key, value in row.items():
        canonical = header_map.get(raw_key)
        if canonical is None:
            continue
        value = (value or "").strip()
        if not value:
            continue
        mapped[canonical] = value
    return mapped


def start_import_batch(conn: sqlite3.Connection, source: str, file_name: str) -> int:
    cur = conn.execute(
        "INSERT INTO import_batches (source, file_name) VALUES (?, ?)",
        (source, file_name),
    )
    conn.commit()
    return cur.lastrowid


def finish_import_batch(
    conn: sqlite3.Connection,
    batch_id: int,
    *,
    total_rows: int,
    new_persons: int,
    matched_persons: int,
    duplicate_candidates_created: int,
    errors: list[dict[str, Any]],
    note: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE import_batches
        SET total_rows = ?, new_persons = ?, matched_persons = ?,
            duplicate_candidates_created = ?, errors_json = ?, note = ?
        WHERE id = ?
        """,
        (
            total_rows,
            new_persons,
            matched_persons,
            duplicate_candidates_created,
            json.dumps(errors, ensure_ascii=False) if errors else None,
            note,
            batch_id,
        ),
    )
    conn.commit()


def upsert_person_from_row(
    conn: sqlite3.Connection,
    mapped: dict[str, Any],
    *,
    source: str,
    default_org_type: str = "company",
    import_batch_id: int | None = None,
) -> dict[str, Any]:
    """1行(マップ済み辞書)から組織を解決し、person をdedup付きで登録する。"""
    org_id = None
    if mapped.get("organization_name"):
        org_id = db.find_or_create_organization(
            conn, mapped["organization_name"], org_type=default_org_type
        )

    record = {
        "name": mapped.get("name"),
        "name_kana": mapped.get("name_kana"),
        "email": mapped.get("email"),
        "email_secondary": mapped.get("email_secondary"),
        "phone": mapped.get("phone"),
        "organization_id": org_id,
        "organization_name": mapped.get("organization_name"),
        "department": mapped.get("department"),
        "job_title": mapped.get("job_title"),
        "location": mapped.get("location"),
        "source": source,
        "first_met_at": mapped.get("first_met_at"),
        "first_met_context": mapped.get("first_met_context"),
        "notes": mapped.get("notes"),
    }
    return db.upsert_person(conn, record, import_batch_id=import_batch_id)
