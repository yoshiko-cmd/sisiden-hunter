"""SQLite DBアクセス層。重複排除、保存、検索、ステータス更新を担う。

将来のPostgreSQL移行を想定し、SQLite固有の記法(sqlite3モジュール呼び出し以外)は
極力使わない。すべてのSQLは標準的なANSI SQLに近い形で書く。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "sisiden_opportunities.db"

_BUDGET_NUMBER_RE = re.compile(r"[\d,]+")


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def compute_dedup_hash(record: dict[str, Any]) -> str:
    """重複排除用ハッシュを算出する(要件5)。

    API側の一意キー(source + source_key)が取得できる場合はそれを優先し、
    無ければ 案件名+発注機関+公告URL+公告日 の組み合わせから生成する。
    """
    source = (record.get("source") or "").strip()
    source_key = (record.get("source_key") or "").strip()
    if source_key:
        basis = f"{source}:{source_key}"
    else:
        basis = "|".join(
            [
                record.get("project_name") or "",
                record.get("organization_name") or "",
                record.get("external_url") or "",
                record.get("published_date") or "",
            ]
        )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def parse_budget(budget_text: str | None) -> tuple[int | None, int | None]:
    """'3,000,000円' や '1,000,000円〜2,000,000円' 等から金額範囲を抽出する。"""
    if not budget_text:
        return None, None
    numbers = [int(n.replace(",", "")) for n in _BUDGET_NUMBER_RE.findall(budget_text) if n]
    if not numbers:
        return None, None
    return min(numbers), max(numbers)


def build_row(record: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    """collector出力(record)とscorer出力(score dict)からDB行を構築する。"""
    budget_min, budget_max = parse_budget(record.get("budget_text"))
    dedup_hash = compute_dedup_hash(record)

    row = {
        "source": record.get("source", "kkj"),
        "source_key": record.get("source_key"),
        "dedup_hash": dedup_hash,
        "project_name": record.get("project_name"),
        "organization_name": record.get("organization_name"),
        "organization_type": record.get("organization_type"),
        "prefecture": record.get("prefecture"),
        "municipality": record.get("municipality"),
        "category": record.get("category"),
        "procedure_type": record.get("procedure_type"),
        "published_date": record.get("published_date"),
        "deadline": record.get("deadline"),
        "opening_date": record.get("opening_date"),
        "budget_text": record.get("budget_text"),
        "budget_min": budget_min,
        "budget_max": budget_max,
        "external_url": record.get("external_url"),
        "description": record.get("description"),
        "attachment_urls": json.dumps(record.get("attachment_urls") or [], ensure_ascii=False),
        "attachment_names": json.dumps(record.get("attachment_names") or [], ensure_ascii=False),
    }
    row.update(score)
    return row


def save_opportunity(conn: sqlite3.Connection, record: dict[str, Any], score: dict[str, Any]) -> tuple[bool, int]:
    """1件保存する。dedup_hashが既存の場合はスキップしてそのIDを返す。

    戻り値: (is_new, id)
    """
    row = build_row(record, score)
    existing = conn.execute(
        "SELECT id FROM opportunities WHERE dedup_hash = ?", (row["dedup_hash"],)
    ).fetchone()
    if existing:
        return False, existing["id"]

    columns = list(row.keys())
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO opportunities ({', '.join(columns)}) VALUES ({placeholders})"
    cur = conn.execute(sql, [row[c] for c in columns])
    conn.commit()
    return True, cur.lastrowid


def save_opportunities(conn: sqlite3.Connection, records_with_scores: Iterable[tuple[dict, dict]]) -> dict[str, int]:
    """複数件保存し、新規/重複件数を返す。"""
    new_count = 0
    dup_count = 0
    for record, score in records_with_scores:
        is_new, _ = save_opportunity(conn, record, score)
        if is_new:
            new_count += 1
        else:
            dup_count += 1
    return {"new_count": new_count, "duplicate_count": dup_count}


def start_collection_log(conn: sqlite3.Connection, source: str, started_at: str) -> int:
    cur = conn.execute(
        "INSERT INTO collection_logs (source, started_at) VALUES (?, ?)",
        (source, started_at),
    )
    conn.commit()
    return cur.lastrowid


_ALLOWED_STATUSES = {
    "new", "reviewing", "candidate", "proposal", "applied", "won", "lost", "ignored", "expired",
}

_ROW_LIST_COLUMNS = [
    "id", "source", "project_name", "organization_name", "organization_type",
    "prefecture", "municipality", "category", "procedure_type",
    "published_date", "deadline", "opening_date", "budget_text", "budget_min", "budget_max",
    "external_url", "video_match", "documentary_match", "social_issue_match",
    "local_industry_match", "youth_match", "community_match", "education_match",
    "human_story_candidate", "project_story_candidate", "keyword_score", "status",
]

_ROW_DETAIL_COLUMNS = _ROW_LIST_COLUMNS + [
    "description", "attachment_urls", "attachment_names", "source_key",
    "user_priority", "memo", "created_at", "updated_at",
]


def _row_to_dict(row: sqlite3.Row, columns: list[str]) -> dict[str, Any]:
    d = {c: row[c] for c in columns}
    for key in ("attachment_urls", "attachment_names"):
        if key in d and d[key]:
            try:
                d[key] = json.loads(d[key])
            except (TypeError, json.JSONDecodeError):
                d[key] = []
    return d


def search_opportunities(
    conn: sqlite3.Connection,
    *,
    prefecture: str | None = None,
    municipality: str | None = None,
    month: str | None = None,  # "YYYY-MM"
    published_from: str | None = None,
    published_to: str | None = None,
    deadline_from: str | None = None,
    deadline_to: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    keywords: list[str] | None = None,
    video_only: bool = False,
    documentary_only: bool = False,
    youth_only: bool = False,
    social_issue_only: bool = False,
    local_industry_only: bool = False,
    human_story_candidate: bool | None = None,
    project_story_candidate: bool | None = None,
    status: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """要件15: search_opportunitiesツールの検索条件をSQLに変換して実行する。"""
    where: list[str] = []
    params: list[Any] = []

    if prefecture:
        where.append("prefecture = ?")
        params.append(prefecture)
    if municipality:
        where.append("municipality = ?")
        params.append(municipality)
    if month:
        where.append("published_date LIKE ?")
        params.append(f"{month}%")
    if published_from:
        where.append("published_date >= ?")
        params.append(published_from)
    if published_to:
        where.append("published_date <= ?")
        params.append(published_to)
    if deadline_from:
        where.append("deadline >= ?")
        params.append(deadline_from)
    if deadline_to:
        where.append("deadline <= ?")
        params.append(deadline_to)
    if min_score is not None:
        where.append("keyword_score >= ?")
        params.append(min_score)
    if max_score is not None:
        where.append("keyword_score <= ?")
        params.append(max_score)
    if keywords:
        kw_clause = " OR ".join(["(project_name LIKE ? OR description LIKE ?)" for _ in keywords])
        where.append(f"({kw_clause})")
        for kw in keywords:
            params.extend([f"%{kw}%", f"%{kw}%"])
    if video_only:
        where.append("video_match = 1")
    if documentary_only:
        where.append("documentary_match = 1")
    if youth_only:
        where.append("youth_match = 1")
    if social_issue_only:
        where.append("social_issue_match = 1")
    if local_industry_only:
        where.append("local_industry_match = 1")
    if human_story_candidate is not None:
        where.append("human_story_candidate = ?")
        params.append(int(human_story_candidate))
    if project_story_candidate is not None:
        where.append("project_story_candidate = ?")
        params.append(int(project_story_candidate))
    if status:
        where.append("status = ?")
        params.append(status)

    sql = f"SELECT {', '.join(_ROW_LIST_COLUMNS)} FROM opportunities"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY documentary_match DESC, keyword_score DESC, published_date DESC"
    sql += " LIMIT ?"
    params.append(max(1, min(int(limit or 30), 200)))

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r, _ROW_LIST_COLUMNS) for r in rows]


def get_opportunity_by_id(conn: sqlite3.Connection, opportunity_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {', '.join(_ROW_DETAIL_COLUMNS)} FROM opportunities WHERE id = ?", (opportunity_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row, _ROW_DETAIL_COLUMNS)


def update_opportunity_status(
    conn: sqlite3.Connection,
    opportunity_id: int,
    *,
    status: str | None = None,
    memo: str | None = None,
    user_priority: int | None = None,
) -> dict[str, Any] | None:
    """要件18: ユーザー判断(ステータス/メモ/優先度)を保存する。"""
    if status is not None and status not in _ALLOWED_STATUSES:
        raise ValueError(f"不正なstatusです: {status} (許可値: {sorted(_ALLOWED_STATUSES)})")

    sets: list[str] = ["updated_at = datetime('now')"]
    params: list[Any] = []
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if memo is not None:
        sets.append("memo = ?")
        params.append(memo)
    if user_priority is not None:
        sets.append("user_priority = ?")
        params.append(user_priority)

    params.append(opportunity_id)
    conn.execute(f"UPDATE opportunities SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    return get_opportunity_by_id(conn, opportunity_id)


def list_top_opportunities(
    conn: sqlite3.Connection,
    *,
    period: str | None = None,  # "YYYY-MM"
    prefecture: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """要件19: documentary_match > keyword_score > 締切までの日数 > 新着順 でランキングする。"""
    where: list[str] = ["status NOT IN ('ignored', 'expired', 'lost')"]
    params: list[Any] = []
    if period:
        where.append("published_date LIKE ?")
        params.append(f"{period}%")
    if prefecture:
        where.append("prefecture = ?")
        params.append(prefecture)

    sql = f"""
        SELECT {', '.join(_ROW_LIST_COLUMNS)}
        FROM opportunities
        WHERE {' AND '.join(where)}
        ORDER BY
            documentary_match DESC,
            keyword_score DESC,
            CASE WHEN deadline IS NULL OR deadline = '' THEN 1 ELSE 0 END,
            deadline ASC,
            published_date DESC
        LIMIT ?
    """
    params.append(max(1, min(int(limit or 20), 200)))
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r, _ROW_LIST_COLUMNS) for r in rows]


def finish_collection_log(
    conn: sqlite3.Connection,
    log_id: int,
    *,
    finished_at: str,
    fetched_count: int,
    new_count: int,
    duplicate_count: int,
    error_count: int,
    duration_seconds: float,
    note: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE collection_logs
        SET finished_at = ?, fetched_count = ?, new_count = ?, duplicate_count = ?,
            error_count = ?, duration_seconds = ?, note = ?
        WHERE id = ?
        """,
        (finished_at, fetched_count, new_count, duplicate_count, error_count, duration_seconds, note, log_id),
    )
    conn.commit()
