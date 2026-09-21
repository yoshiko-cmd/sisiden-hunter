"""MCPツールのビジネスロジック(要件15〜19)。

server.py から呼び出される。DB接続はツール呼び出しごとに開閉する
(MCP Serverはステートレスなツール呼び出しを想定しているため)。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.attachments.downloader import download_specification
from src.attachments.enrich import enrich_opportunity
from src.attachments.extractor import load_extraction
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
    deadline_verified: bool | None = None,
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
            deadline_verified=deadline_verified,
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


DEFAULT_MAX_CHARS = 6000


def get_specification_text(
    id: int,
    attachment_index: int = 0,
    page_from: int = 1,
    page_to: int | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    """仕様書PDFから抽出したテキストを、ページ範囲を指定して取得する。

    全文を一度に返さない。未抽出の場合はその場でダウンロード・抽出を実行する。
    """
    conn = get_connection(db_path)
    try:
        opp = get_opportunity_by_id(conn, id)
        if opp is None:
            return {"found": False, "error": f"id={id} の案件は見つかりません"}

        documents = load_extraction(id)
        if documents is None:
            result = enrich_opportunity(conn, id)
            if result["status"] != "extracted":
                return {
                    "found": True,
                    "extracted": False,
                    "status": result["status"],
                    "message": {
                        "no_attachment": "この案件には添付資料の登録がありません",
                        "download_failed": "添付資料をダウンロードできませんでした",
                        "empty": "PDFにテキストが埋め込まれていません(画像スキャンの可能性)。外部OCRは使用していません",
                    }.get(result["status"], "仕様書テキストを取得できませんでした"),
                    "errors": result.get("errors"),
                }
            documents = load_extraction(id) or []
    finally:
        conn.close()

    catalog = [
        {
            "attachment_index": i,
            "file_name": d.get("file_name"),
            "page_count": d.get("page_count", 0),
            "char_count": d.get("char_count", 0),
            "status": d.get("status"),
            "note": d.get("note"),
        }
        for i, d in enumerate(documents)
    ]

    if not documents:
        return {"found": True, "extracted": False, "attachments": catalog, "message": "抽出結果がありません"}

    if not 0 <= attachment_index < len(documents):
        return {
            "found": True,
            "error": f"attachment_index={attachment_index} は範囲外です(0〜{len(documents) - 1})",
            "attachments": catalog,
        }

    doc = documents[attachment_index]
    pages = doc.get("pages") or []
    total_pages = len(pages)

    start = max(1, page_from)
    end = total_pages if page_to is None else min(page_to, total_pages)

    if start > total_pages:
        return {
            "found": True,
            "error": f"page_from={page_from} は範囲外です(総ページ数{total_pages})",
            "attachments": catalog,
        }

    selected = pages[start - 1 : end]
    text = "\n\n".join(f"--- p.{start + i} ---\n{t}" for i, t in enumerate(selected))

    truncated = False
    last_page_returned = end
    if len(text) > max_chars:
        # 文字数上限を超える場合はページ単位で切り、どこまで返したかを明示する
        accumulated: list[str] = []
        length = 0
        last_page_returned = start - 1
        for i, page_text in enumerate(selected):
            block = f"--- p.{start + i} ---\n{page_text}"
            if length + len(block) > max_chars and accumulated:
                break
            accumulated.append(block)
            length += len(block)
            last_page_returned = start + i
        text = "\n\n".join(accumulated)[:max_chars]
        truncated = True

    return {
        "found": True,
        "extracted": True,
        "project_name": opp["project_name"],
        "attachments": catalog,
        "attachment_index": attachment_index,
        "file_name": doc.get("file_name"),
        "total_pages": total_pages,
        "page_from": start,
        "page_to": last_page_returned,
        "has_more": last_page_returned < total_pages,
        "truncated": truncated,
        "next_page_from": last_page_returned + 1 if last_page_returned < total_pages else None,
        "text": text,
    }


def update_opportunity_status(
    id: int,
    status: str | None = None,
    memo: str | None = None,
    user_priority: int | None = None,
    application_deadline: str | None = None,
    deadline_source: str | None = None,
    db_path: str = str(DEFAULT_DB_PATH),
) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        result = _update_opportunity_status(
            conn,
            id,
            status=status,
            memo=memo,
            user_priority=user_priority,
            application_deadline=application_deadline,
            deadline_source=deadline_source,
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
