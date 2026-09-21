"""SISIDEN Relationship OS のDBアクセス層。

思想: 「人物」を中心に、組織・タグ・接点・案件・キャンペーンをすべて1つのDBで扱う。
営業とPRを別テーブルに分けない。重複登録の防止(メール最優先、他は人間確認)を
アプリ側の責務として持つ。

将来のPostgreSQL移行を想定し、SQLite固有の記法(sqlite3モジュール呼び出し以外)は
極力使わない。
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "sisiden_relationship.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 正規化ヘルパー
# ============================================================

def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return value or None


_PHONE_STRIP_RE = re.compile(r"[^\d]")


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = _PHONE_STRIP_RE.sub("", value)
    # 先頭の国番号(81)は付け外しどちらもあり得るため、0始まりの国内形式に寄せる
    if digits.startswith("81") and len(digits) > 10:
        digits = "0" + digits[2:]
    return digits or None


def _now_sql() -> str:
    return "datetime('now')"


# ============================================================
# ORGANIZATION
# ============================================================

_ORG_TYPES = {"company", "municipality", "school", "university", "media", "ngo", "association", "other"}


def find_organization_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    name = (name or "").strip()
    if not name:
        return None
    return conn.execute(
        "SELECT * FROM organizations WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()


def find_or_create_organization(
    conn: sqlite3.Connection,
    name: str | None,
    *,
    org_type: str = "other",
    industry: str | None = None,
    location: str | None = None,
    website: str | None = None,
) -> int | None:
    """組織名から既存組織を探し、無ければ作成する。名前が空ならNoneを返す。"""
    name = (name or "").strip()
    if not name:
        return None
    existing = find_organization_by_name(conn, name)
    if existing:
        # 空欄だけ補完する(既存の入力を勝手に上書きしない)
        updates: dict[str, Any] = {}
        if industry and not existing["industry"]:
            updates["industry"] = industry
        if location and not existing["location"]:
            updates["location"] = location
        if website and not existing["website"]:
            updates["website"] = website
        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE organizations SET {sets}, updated_at = {_now_sql()} WHERE id = ?",
                [*updates.values(), existing["id"]],
            )
            conn.commit()
        return existing["id"]

    if org_type not in _ORG_TYPES:
        org_type = "other"
    cur = conn.execute(
        """
        INSERT INTO organizations (name, type, industry, location, website)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, org_type, industry, location, website),
    )
    conn.commit()
    return cur.lastrowid


def get_organization_detail(conn: sqlite3.Connection, organization_id: int) -> dict[str, Any] | None:
    org = conn.execute("SELECT * FROM organizations WHERE id = ?", (organization_id,)).fetchone()
    if org is None:
        return None
    persons = conn.execute(
        """
        SELECT id, name, department, job_title, email, relationship_strength, last_contact_at
        FROM persons
        WHERE organization_id = ? AND is_deleted = 0
        ORDER BY relationship_strength DESC, last_contact_at DESC
        """,
        (organization_id,),
    ).fetchall()
    result = dict(org)
    result["persons"] = [dict(p) for p in persons]
    return result


def search_organizations(
    conn: sqlite3.Connection,
    *,
    text: str | None = None,
    org_type: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if text:
        where.append("(name LIKE ? OR notes LIKE ?)")
        params.extend([f"%{text}%", f"%{text}%"])
    if org_type:
        where.append("type = ?")
        params.append(org_type)
    if industry:
        where.append("industry LIKE ?")
        params.append(f"%{industry}%")
    if location:
        where.append("location LIKE ?")
        params.append(f"%{location}%")
    sql = "SELECT * FROM organizations"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY name LIMIT ?"
    params.append(max(1, min(int(limit or 50), 200)))
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# TAG
# ============================================================

def get_or_create_tag(conn: sqlite3.Connection, name: str, category: str | None = None) -> int:
    name = name.strip()
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO tags (name, category) VALUES (?, ?)", (name, category))
    conn.commit()
    return cur.lastrowid


def add_person_tags(conn: sqlite3.Connection, person_id: int, tag_names: Iterable[str], category: str | None = None) -> None:
    for raw in tag_names:
        name = (raw or "").strip()
        if not name:
            continue
        tag_id = get_or_create_tag(conn, name, category)
        conn.execute(
            "INSERT OR IGNORE INTO person_tags (person_id, tag_id) VALUES (?, ?)",
            (person_id, tag_id),
        )
    conn.commit()


def get_person_tags(conn: sqlite3.Connection, person_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT t.name FROM tags t
        JOIN person_tags pt ON pt.tag_id = t.id
        WHERE pt.person_id = ?
        ORDER BY t.name
        """,
        (person_id,),
    ).fetchall()
    return [r["name"] for r in rows]


# ============================================================
# 重複判定(dedup)
# ============================================================
# 方針(仕様どおり):
#   - メールアドレス完全一致 = 「同一人物」として確定 → 新規行を作らず既存行を更新する
#   - 電話番号 / 氏名+会社名 / 氏名+部署 の一致 = 確信度が低いため自動統合しない。
#     新規行は作成するが、duplicate_candidates に候補として記録し、人間の確認を待つ。

DedupMatch = tuple[int, str, str]  # (person_id, basis, confidence)


def find_duplicate_candidates(
    conn: sqlite3.Connection,
    *,
    name: str | None,
    email: str | None,
    phone: str | None,
    organization_name: str | None,
    department: str | None,
    exclude_person_id: int | None = None,
) -> list[DedupMatch]:
    """email以外の手がかりで重複候補を探す(email一致はfind_person_by_emailで別扱い)。"""
    matches: dict[int, DedupMatch] = {}

    def _add(rows: Iterable[sqlite3.Row], basis: str, confidence: str) -> None:
        for row in rows:
            pid = row["id"]
            if exclude_person_id is not None and pid == exclude_person_id:
                continue
            if pid not in matches:
                matches[pid] = (pid, basis, confidence)

    norm_phone = normalize_phone(phone)
    if norm_phone:
        rows = conn.execute(
            "SELECT id FROM persons WHERE phone = ? AND is_deleted = 0", (norm_phone,)
        ).fetchall()
        _add(rows, "phone", "medium")

    name = (name or "").strip()
    org_name = (organization_name or "").strip()
    dept = (department or "").strip()

    if name and org_name:
        rows = conn.execute(
            """
            SELECT p.id FROM persons p
            JOIN organizations o ON o.id = p.organization_id
            WHERE p.name = ? COLLATE NOCASE AND o.name = ? COLLATE NOCASE AND p.is_deleted = 0
            """,
            (name, org_name),
        ).fetchall()
        _add(rows, "name_org", "medium")

    if name and dept:
        rows = conn.execute(
            "SELECT id FROM persons WHERE name = ? COLLATE NOCASE AND department = ? COLLATE NOCASE AND is_deleted = 0",
            (name, dept),
        ).fetchall()
        _add(rows, "name_dept", "low")

    return list(matches.values())


def find_person_by_email(conn: sqlite3.Connection, email: str | None) -> sqlite3.Row | None:
    norm = normalize_email(email)
    if not norm:
        return None
    return conn.execute(
        "SELECT * FROM persons WHERE (email = ? OR email_secondary = ?) AND is_deleted = 0",
        (norm, norm),
    ).fetchone()


_PERSON_FIELDS = [
    "name", "name_kana", "email", "email_secondary", "phone", "organization_id",
    "department", "job_title", "location", "source", "source_id",
    "first_met_at", "first_met_context", "notes",
]


def upsert_person(
    conn: sqlite3.Connection,
    record: dict[str, Any],
    *,
    import_batch_id: int | None = None,
) -> dict[str, Any]:
    """人物を登録する。重複判定を内蔵する。

    戻り値: {"person_id": int, "action": "matched_email" | "created" | "created_with_duplicate_candidates",
              "duplicate_candidate_ids": list[int]}
    """
    email = normalize_email(record.get("email"))
    phone = normalize_phone(record.get("phone"))
    name = (record.get("name") or "").strip()
    if not name:
        raise ValueError("氏名(name)は必須です")

    existing = find_person_by_email(conn, email)
    if existing is not None:
        # メール一致 = 確定。空欄だけ補完し、新しい接点情報として first_met等は上書きしない。
        updates: dict[str, Any] = {}
        for field in _PERSON_FIELDS:
            if field in ("email", "source", "source_id"):
                continue
            new_val = record.get(field)
            if field == "phone":
                new_val = phone
            if new_val and not existing[field]:
                updates[field] = new_val
        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE persons SET {sets}, updated_at = {_now_sql()} WHERE id = ?",
                [*updates.values(), existing["id"]],
            )
            conn.commit()
        _record_person_source(conn, existing["id"], record.get("source", "manual"), record.get("source_id"), import_batch_id)
        return {"person_id": existing["id"], "action": "matched_email", "duplicate_candidate_ids": []}

    organization_name = record.get("organization_name")
    department = record.get("department")
    dup_matches = find_duplicate_candidates(
        conn,
        name=name,
        email=None,
        phone=phone,
        organization_name=organization_name,
        department=department,
    )

    cur = conn.execute(
        """
        INSERT INTO persons (
            name, name_kana, email, email_secondary, phone, organization_id,
            department, job_title, location, source, source_id,
            first_met_at, first_met_context, last_contact_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            record.get("name_kana"),
            email,
            normalize_email(record.get("email_secondary")),
            phone,
            record.get("organization_id"),
            department,
            record.get("job_title"),
            record.get("location"),
            record.get("source", "manual"),
            record.get("source_id"),
            record.get("first_met_at"),
            record.get("first_met_context"),
            record.get("first_met_at"),
            record.get("notes"),
        ),
    )
    person_id = cur.lastrowid
    conn.commit()
    _record_person_source(conn, person_id, record.get("source", "manual"), record.get("source_id"), import_batch_id)

    dup_ids: list[int] = []
    for other_id, basis, confidence in dup_matches:
        a, b = sorted((person_id, other_id))
        try:
            dup_cur = conn.execute(
                """
                INSERT INTO duplicate_candidates (person_id_a, person_id_b, match_basis, confidence)
                VALUES (?, ?, ?, ?)
                """,
                (a, b, basis, confidence),
            )
            dup_ids.append(dup_cur.lastrowid)
        except sqlite3.IntegrityError:
            pass  # 既に同じ候補が記録済み
    conn.commit()

    action = "created_with_duplicate_candidates" if dup_ids else "created"
    return {"person_id": person_id, "action": action, "duplicate_candidate_ids": dup_ids}


def _record_person_source(
    conn: sqlite3.Connection,
    person_id: int,
    source: str,
    source_id: str | None,
    import_batch_id: int | None,
) -> None:
    conn.execute(
        "INSERT INTO person_sources (person_id, source, source_id, import_batch_id) VALUES (?, ?, ?, ?)",
        (person_id, source, source_id, import_batch_id),
    )
    conn.commit()


def list_duplicate_candidates(conn: sqlite3.Connection, status: str = "pending", limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT dc.*, pa.name AS name_a, pa.email AS email_a, pb.name AS name_b, pb.email AS email_b
        FROM duplicate_candidates dc
        JOIN persons pa ON pa.id = dc.person_id_a
        JOIN persons pb ON pb.id = dc.person_id_b
        WHERE dc.status = ?
        ORDER BY dc.confidence DESC, dc.detected_at DESC
        LIMIT ?
        """,
        (status, max(1, min(int(limit or 50), 200))),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_duplicate(
    conn: sqlite3.Connection,
    duplicate_id: int,
    *,
    action: str,  # "merge" | "reject"
    keep_person_id: int | None = None,
    resolved_by: str | None = None,
) -> dict[str, Any]:
    dup = conn.execute("SELECT * FROM duplicate_candidates WHERE id = ?", (duplicate_id,)).fetchone()
    if dup is None:
        return {"found": False, "error": f"duplicate_id={duplicate_id} が見つかりません"}

    if action == "reject":
        conn.execute(
            f"UPDATE duplicate_candidates SET status = 'rejected', resolved_at = {_now_sql()}, resolved_by = ? WHERE id = ?",
            (resolved_by, duplicate_id),
        )
        conn.commit()
        return {"found": True, "action": "rejected"}

    if action != "merge":
        raise ValueError("actionは 'merge' か 'reject' のいずれかです")

    person_a, person_b = dup["person_id_a"], dup["person_id_b"]
    keep_id = keep_person_id or person_a
    merge_id = person_b if keep_id == person_a else person_a
    merge_persons(conn, keep_id=keep_id, merge_id=merge_id)

    conn.execute(
        f"UPDATE duplicate_candidates SET status = 'merged', resolved_at = {_now_sql()}, resolved_by = ? WHERE id = ?",
        (resolved_by, duplicate_id),
    )
    # 同じ2人に対する他の重複候補も解決済みにする
    conn.execute(
        f"""
        UPDATE duplicate_candidates SET status = 'merged', resolved_at = {_now_sql()}, resolved_by = ?
        WHERE status = 'pending' AND
              ((person_id_a = ? AND person_id_b = ?) OR (person_id_a = ? AND person_id_b = ?))
        """,
        (resolved_by, person_a, person_b, person_b, person_a),
    )
    conn.commit()
    return {"found": True, "action": "merged", "kept_person_id": keep_id, "merged_person_id": merge_id}


def merge_persons(conn: sqlite3.Connection, *, keep_id: int, merge_id: int) -> None:
    """merge_id の子レコードをkeep_idへ付け替え、空欄を補完してからmerge_idを削除する。"""
    if keep_id == merge_id:
        return
    keep = conn.execute("SELECT * FROM persons WHERE id = ?", (keep_id,)).fetchone()
    merge = conn.execute("SELECT * FROM persons WHERE id = ?", (merge_id,)).fetchone()
    if keep is None or merge is None:
        raise ValueError("マージ対象の人物が見つかりません")

    updates: dict[str, Any] = {}
    for field in _PERSON_FIELDS:
        if not keep[field] and merge[field]:
            updates[field] = merge[field]
    if merge["relationship_strength"] > keep["relationship_strength"]:
        updates["relationship_strength"] = merge["relationship_strength"]
    if merge["last_contact_at"] and (not keep["last_contact_at"] or merge["last_contact_at"] > keep["last_contact_at"]):
        updates["last_contact_at"] = merge["last_contact_at"]
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE persons SET {sets}, updated_at = {_now_sql()} WHERE id = ?", [*updates.values(), keep_id])

    conn.execute("UPDATE interactions SET person_id = ? WHERE person_id = ?", (keep_id, merge_id))
    conn.execute("INSERT OR IGNORE INTO person_tags (person_id, tag_id) SELECT ?, tag_id FROM person_tags WHERE person_id = ?", (keep_id, merge_id))
    conn.execute("DELETE FROM person_tags WHERE person_id = ?", (merge_id,))
    conn.execute("UPDATE campaign_targets SET person_id = ? WHERE person_id = ? AND NOT EXISTS (SELECT 1 FROM campaign_targets ct2 WHERE ct2.campaign_id = campaign_targets.campaign_id AND ct2.person_id = ?)", (keep_id, merge_id, keep_id))
    conn.execute("DELETE FROM campaign_targets WHERE person_id = ?", (merge_id,))
    conn.execute("UPDATE coverage SET person_id = ? WHERE person_id = ?", (keep_id, merge_id))
    conn.execute("UPDATE person_sources SET person_id = ? WHERE person_id = ?", (keep_id, merge_id))

    merge_media = conn.execute("SELECT * FROM media_profiles WHERE person_id = ?", (merge_id,)).fetchone()
    keep_media = conn.execute("SELECT * FROM media_profiles WHERE person_id = ?", (keep_id,)).fetchone()
    if merge_media and not keep_media:
        conn.execute("UPDATE media_profiles SET person_id = ? WHERE person_id = ?", (keep_id, merge_id))
    elif merge_media and keep_media:
        conn.execute("DELETE FROM media_profiles WHERE person_id = ?", (merge_id,))

    conn.execute(
        f"UPDATE persons SET is_deleted = 1, merged_into_id = ?, updated_at = {_now_sql()} WHERE id = ?",
        (keep_id, merge_id),
    )
    conn.commit()


# ============================================================
# PERSON: 詳細取得・検索
# ============================================================

def get_person_detail(conn: sqlite3.Connection, person_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    if result["organization_id"]:
        org = conn.execute("SELECT * FROM organizations WHERE id = ?", (result["organization_id"],)).fetchone()
        result["organization"] = dict(org) if org else None
    else:
        result["organization"] = None
    result["tags"] = get_person_tags(conn, person_id)
    media = conn.execute("SELECT * FROM media_profiles WHERE person_id = ?", (person_id,)).fetchone()
    result["media_profile"] = dict(media) if media else None
    interactions = conn.execute(
        """
        SELECT i.*, p.project_name FROM interactions i
        LEFT JOIN projects p ON p.id = i.project_id
        WHERE i.person_id = ?
        ORDER BY i.date DESC, i.id DESC
        LIMIT 20
        """,
        (person_id,),
    ).fetchall()
    result["recent_interactions"] = [dict(r) for r in interactions]
    return result


_PERSON_SEARCH_COLUMNS = """
    p.id, p.name, p.name_kana, p.email, p.phone, p.department, p.job_title,
    p.location, p.source, p.first_met_at, p.first_met_context, p.last_contact_at,
    p.relationship_strength, p.newsletter_status, p.sales_email_status, p.media_pitch_status,
    p.notes, o.id AS organization_id, o.name AS organization_name, o.type AS organization_type,
    o.industry AS organization_industry
"""


def search_people(
    conn: sqlite3.Connection,
    *,
    text: str | None = None,
    tags: list[str] | None = None,
    match_all_tags: bool = False,
    organization_type: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    job_title_contains: str | None = None,
    source: str | None = None,
    is_media: bool | None = None,
    min_relationship_strength: int | None = None,
    not_contacted_since_days: int | None = None,
    contacted_within_days: int | None = None,
    has_reply: bool | None = None,
    newsletter_status: str | None = None,
    sales_email_status: str | None = None,
    media_pitch_status: str | None = None,
    contactable_for: str | None = None,  # "newsletter" | "sales" | "media_pitch" -> do_not_contact/unsubscribedを除外
    limit: int = 50,
) -> list[dict[str, Any]]:
    where: list[str] = ["p.is_deleted = 0"]
    params: list[Any] = []
    joins = ["LEFT JOIN organizations o ON o.id = p.organization_id"]

    if text:
        where.append(
            "(p.name LIKE ? OR p.name_kana LIKE ? OR p.notes LIKE ? OR o.name LIKE ? OR "
            "EXISTS (SELECT 1 FROM media_profiles mp WHERE mp.person_id = p.id AND "
            "(mp.interest_themes LIKE ? OR mp.genre LIKE ? OR mp.outlet_name LIKE ?)))"
        )
        like = f"%{text}%"
        params.extend([like, like, like, like, like, like, like])

    if tags:
        placeholders = ", ".join("?" for _ in tags)
        if match_all_tags:
            where.append(
                f"""(SELECT COUNT(DISTINCT t.name) FROM person_tags pt JOIN tags t ON t.id = pt.tag_id
                    WHERE pt.person_id = p.id AND t.name IN ({placeholders})) = ?"""
            )
            params.extend(tags)
            params.append(len(tags))
        else:
            where.append(
                f"""EXISTS (SELECT 1 FROM person_tags pt JOIN tags t ON t.id = pt.tag_id
                    WHERE pt.person_id = p.id AND t.name IN ({placeholders}))"""
            )
            params.extend(tags)

    if organization_type:
        where.append("o.type = ?")
        params.append(organization_type)
    if industry:
        where.append("o.industry LIKE ?")
        params.append(f"%{industry}%")
    if location:
        where.append("(p.location LIKE ? OR o.location LIKE ?)")
        params.extend([f"%{location}%", f"%{location}%"])
    if job_title_contains:
        where.append("p.job_title LIKE ?")
        params.append(f"%{job_title_contains}%")
    if source:
        where.append("p.source = ?")
        params.append(source)
    if is_media is not None:
        if is_media:
            where.append("EXISTS (SELECT 1 FROM media_profiles mp WHERE mp.person_id = p.id)")
        else:
            where.append("NOT EXISTS (SELECT 1 FROM media_profiles mp WHERE mp.person_id = p.id)")
    if min_relationship_strength is not None:
        where.append("p.relationship_strength >= ?")
        params.append(min_relationship_strength)
    if not_contacted_since_days is not None:
        where.append(
            f"(p.last_contact_at IS NULL OR p.last_contact_at <= date('now', '-{int(not_contacted_since_days)} days'))"
        )
    if contacted_within_days is not None:
        where.append(
            f"(p.last_contact_at IS NOT NULL AND p.last_contact_at >= date('now', '-{int(contacted_within_days)} days'))"
        )
    if has_reply is not None:
        clause = "EXISTS (SELECT 1 FROM interactions i WHERE i.person_id = p.id AND i.reaction IS NOT NULL AND i.reaction != '')"
        where.append(clause if has_reply else f"NOT {clause}")
    if newsletter_status:
        where.append("p.newsletter_status = ?")
        params.append(newsletter_status)
    if sales_email_status:
        where.append("p.sales_email_status = ?")
        params.append(sales_email_status)
    if media_pitch_status:
        where.append("p.media_pitch_status = ?")
        params.append(media_pitch_status)
    if contactable_for in ("newsletter", "sales", "media_pitch"):
        col = {"newsletter": "newsletter_status", "sales": "sales_email_status", "media_pitch": "media_pitch_status"}[contactable_for]
        where.append(f"p.{col} NOT IN ('unsubscribed', 'do_not_contact')")

    sql = f"SELECT {_PERSON_SEARCH_COLUMNS} FROM persons p {' '.join(joins)}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY p.relationship_strength DESC, p.last_contact_at DESC"
    sql += " LIMIT ?"
    params.append(max(1, min(int(limit or 50), 300)))

    rows = conn.execute(sql, params).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["tags"] = get_person_tags(conn, d["id"])
        results.append(d)
    return results


def set_optout(
    conn: sqlite3.Connection,
    person_id: int,
    channel: str,  # "newsletter" | "sales" | "media_pitch"
    status: str,  # "subscribed"/"allowed" | "unsubscribed" | "do_not_contact"
) -> dict[str, Any] | None:
    col = {"newsletter": "newsletter_status", "sales": "sales_email_status", "media_pitch": "media_pitch_status"}.get(channel)
    if col is None:
        raise ValueError("channelは newsletter/sales/media_pitch のいずれかです")
    conn.execute(f"UPDATE persons SET {col} = ?, updated_at = {_now_sql()} WHERE id = ?", (status, person_id))
    conn.commit()
    return get_person_detail(conn, person_id)


def update_relationship_strength(conn: sqlite3.Connection, person_id: int, delta: int, cap: int = 100) -> None:
    conn.execute(
        f"""
        UPDATE persons
        SET relationship_strength = MIN(?, MAX(0, relationship_strength + ?)),
            updated_at = {_now_sql()}
        WHERE id = ?
        """,
        (cap, delta, person_id),
    )
    conn.commit()


# ============================================================
# MEDIA_PROFILE
# ============================================================

def upsert_media_profile(conn: sqlite3.Connection, person_id: int, fields: dict[str, Any]) -> int:
    existing = conn.execute("SELECT id FROM media_profiles WHERE person_id = ?", (person_id,)).fetchone()
    cols = ["outlet_name", "genre", "area", "interest_themes", "past_article_urls", "last_contacted_at", "reply_notes"]
    values = {c: fields.get(c) for c in cols if fields.get(c) is not None}
    if "past_article_urls" in values and not isinstance(values["past_article_urls"], str):
        values["past_article_urls"] = json.dumps(values["past_article_urls"], ensure_ascii=False)

    if existing:
        if values:
            sets = ", ".join(f"{k} = ?" for k in values)
            conn.execute(
                f"UPDATE media_profiles SET {sets}, updated_at = {_now_sql()} WHERE person_id = ?",
                [*values.values(), person_id],
            )
            conn.commit()
        return existing["id"]

    columns = ["person_id", *values.keys()]
    placeholders = ", ".join("?" for _ in columns)
    cur = conn.execute(
        f"INSERT INTO media_profiles ({', '.join(columns)}) VALUES ({placeholders})",
        [person_id, *values.values()],
    )
    conn.commit()
    add_person_tags(conn, person_id, ["メディア"], category="role")
    return cur.lastrowid


# ============================================================
# PROJECT
# ============================================================

def create_project(conn: sqlite3.Connection, fields: dict[str, Any]) -> int:
    keywords = fields.get("keywords")
    if isinstance(keywords, list):
        keywords = json.dumps(keywords, ensure_ascii=False)
    cur = conn.execute(
        """
        INSERT INTO projects (
            project_name, client, description, status, release_date, location,
            main_theme, social_issue, industry, keywords, target_audience,
            related_url, video_url, article_url, opportunity_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fields["project_name"],
            fields.get("client"),
            fields.get("description"),
            fields.get("status", "planning"),
            fields.get("release_date"),
            fields.get("location"),
            fields.get("main_theme"),
            fields.get("social_issue"),
            fields.get("industry"),
            keywords,
            fields.get("target_audience"),
            fields.get("related_url"),
            fields.get("video_url"),
            fields.get("article_url"),
            fields.get("opportunity_id"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def _project_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("keywords"):
        try:
            d["keywords"] = json.loads(d["keywords"])
        except (TypeError, json.JSONDecodeError):
            d["keywords"] = []
    else:
        d["keywords"] = []
    return d


def get_project(conn: sqlite3.Connection, project_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    result = _project_row_to_dict(row)
    coverage = conn.execute(
        "SELECT * FROM coverage WHERE project_id = ? ORDER BY published_date DESC", (project_id,)
    ).fetchall()
    result["coverage"] = [dict(c) for c in coverage]
    contents = conn.execute(
        "SELECT * FROM contents WHERE project_id = ? ORDER BY published_date DESC", (project_id,)
    ).fetchall()
    result["contents"] = [dict(c) for c in contents]
    return result


def search_projects(conn: sqlite3.Connection, *, text: str | None = None, status: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if text:
        where.append("(project_name LIKE ? OR client LIKE ? OR description LIKE ? OR main_theme LIKE ? OR social_issue LIKE ?)")
        like = f"%{text}%"
        params.extend([like, like, like, like, like])
    if status:
        where.append("status = ?")
        params.append(status)
    sql = "SELECT * FROM projects"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit or 30), 200)))
    rows = conn.execute(sql, params).fetchall()
    return [_project_row_to_dict(r) for r in rows]


# ============================================================
# INTERACTION
# ============================================================

_CHANNELS = {"email", "meeting", "business_card", "phone", "event", "newsletter", "media_pitch", "sns", "introduction"}


def log_interaction(conn: sqlite3.Connection, fields: dict[str, Any]) -> int:
    channel = fields.get("channel")
    if channel not in _CHANNELS:
        raise ValueError(f"不正なchannelです: {channel} (許可値: {sorted(_CHANNELS)})")
    cur = conn.execute(
        """
        INSERT INTO interactions (
            person_id, project_id, date, channel, direction, subject, summary,
            reaction, next_action, next_action_date, campaign_id, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fields["person_id"],
            fields.get("project_id"),
            fields["date"],
            channel,
            fields.get("direction", "outbound"),
            fields.get("subject"),
            fields.get("summary"),
            fields.get("reaction"),
            fields.get("next_action"),
            fields.get("next_action_date"),
            fields.get("campaign_id"),
            fields.get("created_by"),
        ),
    )
    interaction_id = cur.lastrowid

    conn.execute(
        f"""
        UPDATE persons SET last_contact_at = ?, updated_at = {_now_sql()}
        WHERE id = ? AND (last_contact_at IS NULL OR last_contact_at < ?)
        """,
        (fields["date"], fields["person_id"], fields["date"]),
    )
    if fields.get("reaction"):
        update_relationship_strength(conn, fields["person_id"], delta=5)
    else:
        update_relationship_strength(conn, fields["person_id"], delta=2)
    conn.commit()
    return interaction_id


# ============================================================
# CAMPAIGN
# ============================================================

def create_campaign(conn: sqlite3.Connection, fields: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO campaigns (name, project_id, campaign_type, status, start_date, end_date, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fields["name"],
            fields.get("project_id"),
            fields.get("campaign_type", "mixed"),
            fields.get("status", "draft"),
            fields.get("start_date"),
            fields.get("end_date"),
            fields.get("notes"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def add_campaign_audience(conn: sqlite3.Connection, campaign_id: int, audience_label: str, filter_json: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO campaign_audiences (campaign_id, audience_label, filter_json) VALUES (?, ?, ?)",
        (campaign_id, audience_label, filter_json),
    )
    conn.commit()
    return cur.lastrowid


def add_campaign_targets(
    conn: sqlite3.Connection,
    campaign_id: int,
    targets: list[dict[str, Any]],
    audience_id: int | None = None,
) -> list[int]:
    ids: list[int] = []
    for t in targets:
        try:
            cur = conn.execute(
                """
                INSERT INTO campaign_targets (campaign_id, audience_id, person_id, category, score, reason, draft_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    audience_id,
                    t["person_id"],
                    t["category"],
                    t.get("score"),
                    t.get("reason"),
                    t.get("draft_text"),
                ),
            )
            ids.append(cur.lastrowid)
        except sqlite3.IntegrityError:
            pass  # 既に同じcampaignに同じ人物が登録済み
    conn.commit()
    return ids


def update_campaign_target_status(
    conn: sqlite3.Connection,
    campaign_target_id: int,
    *,
    status: str,
    approved_by: str | None = None,
    draft_text: str | None = None,
) -> dict[str, Any] | None:
    """人間の承認/送信ステップ。statusが'sent'になったらInteractionを自動生成する(STEP7→8)。"""
    allowed = {"candidate", "approved", "rejected", "sent"}
    if status not in allowed:
        raise ValueError(f"不正なstatusです: {status} (許可値: {sorted(allowed)})")

    target = conn.execute("SELECT * FROM campaign_targets WHERE id = ?", (campaign_target_id,)).fetchone()
    if target is None:
        return None

    sets = ["status = ?", f"updated_at = {_now_sql()}"]
    params: list[Any] = [status]
    if draft_text is not None:
        sets.append("draft_text = ?")
        params.append(draft_text)
    if status == "approved":
        sets.append("approved_by = ?")
        params.append(approved_by)
        sets.append(f"approved_at = {_now_sql()}")
    if status == "sent":
        sets.append(f"sent_at = {_now_sql()}")

    params.append(campaign_target_id)
    conn.execute(f"UPDATE campaign_targets SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()

    if status == "sent":
        campaign = conn.execute("SELECT * FROM campaigns WHERE id = ?", (target["campaign_id"],)).fetchone()
        channel_map = {"MEDIA": "media_pitch", "SALES": "email", "RELATIONSHIP": "newsletter", "AMPLIFICATION": "introduction"}
        from datetime import date as _date

        log_interaction(
            conn,
            {
                "person_id": target["person_id"],
                "project_id": campaign["project_id"] if campaign else None,
                "date": _date.today().isoformat(),
                "channel": channel_map.get(target["category"], "email"),
                "direction": "outbound",
                "subject": campaign["name"] if campaign else None,
                "summary": draft_text or target["draft_text"] or target["reason"],
                "campaign_id": target["campaign_id"],
                "created_by": approved_by,
            },
        )

    row = conn.execute("SELECT * FROM campaign_targets WHERE id = ?", (campaign_target_id,)).fetchone()
    return dict(row) if row else None


def list_campaign_targets(conn: sqlite3.Connection, campaign_id: int, category: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    where = ["ct.campaign_id = ?"]
    params: list[Any] = [campaign_id]
    if category:
        where.append("ct.category = ?")
        params.append(category)
    if status:
        where.append("ct.status = ?")
        params.append(status)
    rows = conn.execute(
        f"""
        SELECT ct.*, p.name AS person_name, p.email AS person_email, o.name AS organization_name
        FROM campaign_targets ct
        JOIN persons p ON p.id = ct.person_id
        LEFT JOIN organizations o ON o.id = p.organization_id
        WHERE {' AND '.join(where)}
        ORDER BY ct.category, ct.score DESC
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# COVERAGE
# ============================================================

def record_coverage(conn: sqlite3.Connection, fields: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO coverage (project_id, person_id, organization_id, published_date, outlet_name, url, triggered_by_interaction_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fields.get("project_id"),
            fields.get("person_id"),
            fields.get("organization_id"),
            fields.get("published_date"),
            fields.get("outlet_name"),
            fields.get("url"),
            fields.get("triggered_by_interaction_id"),
            fields.get("notes"),
        ),
    )
    conn.commit()
    if fields.get("person_id"):
        update_relationship_strength(conn, fields["person_id"], delta=10)
    return cur.lastrowid


# ============================================================
# DASHBOARD
# ============================================================

def get_dashboard(conn: sqlite3.Connection) -> dict[str, Any]:
    active_projects = conn.execute(
        "SELECT id, project_name, status, release_date FROM projects WHERE status IN ('planning', 'in_production') ORDER BY updated_at DESC LIMIT 10"
    ).fetchall()

    due_follow_ups = conn.execute(
        """
        SELECT i.id, i.person_id, p.name AS person_name, i.next_action, i.next_action_date, i.project_id
        FROM interactions i JOIN persons p ON p.id = i.person_id
        WHERE i.next_action_date IS NOT NULL AND i.next_action_date <= date('now', '+7 days')
        ORDER BY i.next_action_date ASC LIMIT 20
        """
    ).fetchall()

    stale_important = conn.execute(
        """
        SELECT id, name, relationship_strength, last_contact_at
        FROM persons
        WHERE is_deleted = 0 AND relationship_strength >= 30
              AND (last_contact_at IS NULL OR last_contact_at <= date('now', '-180 days'))
        ORDER BY relationship_strength DESC LIMIT 15
        """
    ).fetchall()

    recent_replies = conn.execute(
        """
        SELECT i.id, i.person_id, p.name AS person_name, i.date, i.reaction, i.project_id
        FROM interactions i JOIN persons p ON p.id = i.person_id
        WHERE i.reaction IS NOT NULL AND i.reaction != ''
        ORDER BY i.date DESC LIMIT 15
        """
    ).fetchall()

    recent_coverage = conn.execute(
        "SELECT * FROM coverage ORDER BY published_date DESC LIMIT 10"
    ).fetchall()

    campaigns_this_month = conn.execute(
        "SELECT * FROM campaigns WHERE start_date >= date('now', 'start of month') OR created_at >= datetime('now', 'start of month') ORDER BY created_at DESC LIMIT 10"
    ).fetchall()

    pending_duplicates = conn.execute(
        "SELECT COUNT(*) AS c FROM duplicate_candidates WHERE status = 'pending'"
    ).fetchone()["c"]

    return {
        "active_projects": [dict(r) for r in active_projects],
        "due_follow_ups": [dict(r) for r in due_follow_ups],
        "stale_important_contacts": [dict(r) for r in stale_important],
        "recent_replies": [dict(r) for r in recent_replies],
        "recent_coverage": [dict(r) for r in recent_coverage],
        "campaigns_this_month": [dict(r) for r in campaigns_this_month],
        "pending_duplicate_candidates": pending_duplicates,
    }
