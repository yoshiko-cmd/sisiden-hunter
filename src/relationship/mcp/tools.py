"""SISIDEN Relationship OS MCPツールのビジネスロジック。

server.py から呼び出される。DB接続はツール呼び出しごとに開閉する
(既存の自治体案件ハンターMCPと同じ流儀)。

このモジュールが行うのはDB検索・スコア計算・集計のみ(ルールベース)。
文面生成・戦略判断はMCPクライアント(Claude)側の役割であり、ここでは行わない。
外部送信(メール送信等)もこのモジュールには存在しない(人間承認が必須のため)。
"""
from __future__ import annotations

from typing import Any

from src.relationship.database import db
from src.relationship.database.db import DEFAULT_DB_PATH
from src.relationship.matching.scorer import recommend_people_for_project as _recommend


def _conn(db_path: str):
    return db.get_connection(db_path)


# ============================================================
# PERSON
# ============================================================

def search_people(db_path: str = str(DEFAULT_DB_PATH), **kwargs: Any) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        results = db.search_people(conn, **kwargs)
    finally:
        conn.close()
    return {"count": len(results), "results": results}


def get_person(id: int, db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        result = db.get_person_detail(conn, id)
    finally:
        conn.close()
    if result is None:
        return {"found": False, "error": f"person_id={id} は見つかりません"}
    return {"found": True, "person": result}


def create_person(fields: dict[str, Any], db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        result = db.upsert_person(conn, fields)
    finally:
        conn.close()
    return result


def set_optout(
    person_id: int,
    channel: str,
    status: str,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        result = db.set_optout(conn, person_id, channel, status)
    except ValueError as exc:
        return {"found": False, "error": str(exc)}
    finally:
        conn.close()
    if result is None:
        return {"found": False, "error": f"person_id={person_id} は見つかりません"}
    return {"found": True, "person": result}


def update_media_profile(person_id: int, fields: dict[str, Any], db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        media_id = db.upsert_media_profile(conn, person_id, fields)
        person = db.get_person_detail(conn, person_id)
    finally:
        conn.close()
    return {"media_profile_id": media_id, "person": person}


# ============================================================
# ORGANIZATION
# ============================================================

def search_organizations(db_path: str = str(DEFAULT_DB_PATH), **kwargs: Any) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        results = db.search_organizations(conn, **kwargs)
    finally:
        conn.close()
    return {"count": len(results), "results": results}


def get_organization(id: int, db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        result = db.get_organization_detail(conn, id)
    finally:
        conn.close()
    if result is None:
        return {"found": False, "error": f"organization_id={id} は見つかりません"}
    return {"found": True, "organization": result}


# ============================================================
# PROJECT
# ============================================================

def create_project(fields: dict[str, Any], db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        project_id = db.create_project(conn, fields)
        project = db.get_project(conn, project_id)
    finally:
        conn.close()
    return {"project_id": project_id, "project": project}


def get_project(id: int, db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        result = db.get_project(conn, id)
    finally:
        conn.close()
    if result is None:
        return {"found": False, "error": f"project_id={id} は見つかりません"}
    return {"found": True, "project": result}


def search_projects(db_path: str = str(DEFAULT_DB_PATH), **kwargs: Any) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        results = db.search_projects(conn, **kwargs)
    finally:
        conn.close()
    return {"count": len(results), "results": results}


def recommend_people_for_project(
    project_id: int,
    categories: list[str] | None = None,
    limit_per_category: int = 10,
    min_score: int = 15,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        project = db.get_project(conn, project_id)
        if project is None:
            return {"found": False, "error": f"project_id={project_id} は見つかりません"}
        buckets = _recommend(
            conn,
            project,
            categories=categories,
            limit_per_category=limit_per_category,
            min_score=min_score,
        )
    finally:
        conn.close()
    return {
        "found": True,
        "project_id": project_id,
        "project_name": project["project_name"],
        "candidates": buckets,
        "counts": {k: len(v) for k, v in buckets.items()},
    }


# ============================================================
# INTERACTION
# ============================================================

def log_interaction(fields: dict[str, Any], db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        interaction_id = db.log_interaction(conn, fields)
        person = db.get_person_detail(conn, fields["person_id"])
    except ValueError as exc:
        return {"created": False, "error": str(exc)}
    finally:
        conn.close()
    return {"created": True, "interaction_id": interaction_id, "person": person}


# ============================================================
# CAMPAIGN (STEP5〜STEP8: 文章案生成〜人間確認〜送信〜Interaction保存)
# ============================================================

def create_campaign(fields: dict[str, Any], db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        campaign_id = db.create_campaign(conn, fields)
    finally:
        conn.close()
    return {"campaign_id": campaign_id}


def add_campaign_audience(
    campaign_id: int,
    audience_label: str,
    filter_json: str | None = None,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        audience_id = db.add_campaign_audience(conn, campaign_id, audience_label, filter_json)
    finally:
        conn.close()
    return {"audience_id": audience_id}


def add_campaign_targets(
    campaign_id: int,
    targets: list[dict[str, Any]],
    audience_id: int | None = None,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    """recommend_people_for_project の候補の中から、人間が選んだ対象をキャンペーンに登録する(STEP6)。"""
    conn = _conn(db_path)
    try:
        ids = db.add_campaign_targets(conn, campaign_id, targets, audience_id=audience_id)
    finally:
        conn.close()
    return {"campaign_target_ids": ids, "count": len(ids)}


def list_campaign_targets(
    campaign_id: int,
    category: str | None = None,
    status: str | None = None,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        results = db.list_campaign_targets(conn, campaign_id, category=category, status=status)
    finally:
        conn.close()
    return {"count": len(results), "results": results}


def update_campaign_target_status(
    campaign_target_id: int,
    status: str,
    approved_by: str | None = None,
    draft_text: str | None = None,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    """人間が承認(approved)または送信済み(sent)としてマークする。

    重要: この関数自体はメールや通知を一切送信しない。実際の送信は
    人間(または別途接続する配信サービス)が行い、その結果をここに記録するのみ。
    status='sent' にすると自動的にInteractionが1件記録される(STEP8)。
    """
    conn = _conn(db_path)
    try:
        result = db.update_campaign_target_status(
            conn, campaign_target_id, status=status, approved_by=approved_by, draft_text=draft_text
        )
    except ValueError as exc:
        return {"found": False, "error": str(exc)}
    finally:
        conn.close()
    if result is None:
        return {"found": False, "error": f"campaign_target_id={campaign_target_id} は見つかりません"}
    return {"found": True, "campaign_target": result}


# ============================================================
# COVERAGE
# ============================================================

def record_coverage(fields: dict[str, Any], db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        coverage_id = db.record_coverage(conn, fields)
    finally:
        conn.close()
    return {"coverage_id": coverage_id}


# ============================================================
# DUPLICATE CANDIDATES
# ============================================================

def list_duplicate_candidates(status: str = "pending", limit: int = 50, db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        results = db.list_duplicate_candidates(conn, status=status, limit=limit)
    finally:
        conn.close()
    return {"count": len(results), "results": results}


def resolve_duplicate(
    duplicate_id: int,
    action: str,
    keep_person_id: int | None = None,
    resolved_by: str | None = None,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        result = db.resolve_duplicate(
            conn, duplicate_id, action=action, keep_person_id=keep_person_id, resolved_by=resolved_by
        )
    except ValueError as exc:
        return {"found": False, "error": str(exc)}
    finally:
        conn.close()
    return result


# ============================================================
# DASHBOARD
# ============================================================

def get_dashboard(db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = _conn(db_path)
    try:
        result = db.get_dashboard(conn)
    finally:
        conn.close()
    return result
