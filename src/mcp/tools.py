"""MCPツールのビジネスロジック(要件15〜19)。

server.py から呼び出される。DB接続はツール呼び出しごとに開閉する
(MCP Serverはステートレスなツール呼び出しを想定しているため)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.attachments.downloader import download_specification
from src.database.db import (
    DEFAULT_DB_PATH,
    get_connection,
    get_opportunity_by_id,
)
from src.database.db import list_top_opportunities as _list_top_opportunities
from src.database.db import search_opportunities as _search_opportunities
from src.database.db import update_opportunity_status as _update_opportunity_status


def search_opportunities(
    prefecture: str | None = None,
    municipality: str | None = None,
    month: str | None = None,
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
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        results = _search_opportunities(
            conn,
            prefecture=prefecture,
            municipality=municipality,
            month=month,
            published_from=published_from,
            published_to=published_to,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            min_score=min_score,
            max_score=max_score,
            keywords=keywords,
            video_only=video_only,
            documentary_only=documentary_only,
            youth_only=youth_only,
            social_issue_only=social_issue_only,
            local_industry_only=local_industry_only,
            human_story_candidate=human_story_candidate,
            project_story_candidate=project_story_candidate,
            status=status,
            limit=limit,
        )
    finally:
        conn.close()
    return {"count": len(results), "results": results}


def get_opportunity(id: int, db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        result = get_opportunity_by_id(conn, id)
    finally:
        conn.close()
    if result is None:
        return {"found": False, "error": f"id={id} の案件は見つかりません"}
    return {"found": True, "opportunity": result}


def get_specification(id: int, db_path: str = str(DEFAULT_DB_PATH)) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        opp = get_opportunity_by_id(conn, id)
    finally:
        conn.close()

    if opp is None:
        return {"found": False, "error": f"id={id} の案件は見つかりません"}

    urls = opp.get("attachment_urls") or []
    names = opp.get("attachment_names") or []
    if not urls:
        return {"found": True, "attachments": [], "message": "この案件には添付資料の登録がありません"}

    results = download_specification(id, urls, names)
    attachments = [
        {
            "url": r.url,
            "success": r.success,
            "local_path": r.local_path,
            "error": r.error,
        }
        for r in results
    ]
    return {"found": True, "attachments": attachments}


def update_opportunity_status(
    id: int,
    status: str | None = None,
    memo: str | None = None,
    user_priority: int | None = None,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        result = _update_opportunity_status(
            conn, id, status=status, memo=memo, user_priority=user_priority
        )
    except ValueError as exc:
        return {"found": False, "error": str(exc)}
    finally:
        conn.close()
    if result is None:
        return {"found": False, "error": f"id={id} の案件は見つかりません"}
    return {"found": True, "opportunity": result}


def list_top_opportunities(
    period: str | None = None,
    prefecture: str | None = None,
    limit: int = 20,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        results = _list_top_opportunities(conn, period=period, prefecture=prefecture, limit=limit)
    finally:
        conn.close()
    return {"count": len(results), "results": results}
