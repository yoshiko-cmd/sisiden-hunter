"""候補案件の添付資料を取得・抽出し、本文を含めて再スコアリングする。

「案件名には書かれていないが、仕様書の中にドキュメンタリーと書いてある案件」を
検出することが目的。すべてローカル処理で完結し、LLM APIは使用しない。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.attachments.downloader import ATTACHMENTS_DIR, download_specification
from src.attachments.extractor import (
    ExtractedDocument,
    combined_text,
    extract_pdf_text,
    load_extraction,
    save_extraction,
)
from src.database.db import get_opportunity_by_id
from src.scoring.scorer import score_opportunity

logger = logging.getLogger("sisiden.attachments.enrich")


def _update_scores(
    conn: sqlite3.Connection,
    opportunity_id: int,
    score: dict[str, Any],
    *,
    spec_text_status: str,
    spec_text_chars: int,
    spec_text_pages: int,
    spec_text_note: str | None,
    scored_with_spec_text: bool,
) -> None:
    # scoreが空(抽出できずスコアを更新しない場合)でもSQLが壊れないようにする
    columns = list(score.keys())
    assignments = "".join(f"{c} = ?, " for c in columns)
    conn.execute(
        f"""
        UPDATE opportunities
        SET {assignments}
            spec_text_status = ?,
            spec_text_chars = ?,
            spec_text_pages = ?,
            spec_text_extracted_at = ?,
            spec_text_note = ?,
            scored_with_spec_text = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        [
            *[score[c] for c in columns],
            spec_text_status,
            spec_text_chars,
            spec_text_pages,
            datetime.now(timezone.utc).isoformat(),
            spec_text_note,
            int(scored_with_spec_text),
            opportunity_id,
        ],
    )
    conn.commit()


def enrich_opportunity(
    conn: sqlite3.Connection,
    opportunity_id: int,
    *,
    base_dir: Path = ATTACHMENTS_DIR,
    force: bool = False,
) -> dict[str, Any]:
    """1案件の添付を取得・抽出し、本文を含めて再スコアリングする。

    戻り値: 処理結果のサマリー(status, score_before, score_after 等)
    """
    opp = get_opportunity_by_id(conn, opportunity_id)
    if opp is None:
        return {"id": opportunity_id, "status": "not_found"}

    score_before = opp["keyword_score"]
    urls = opp.get("attachment_urls") or []
    names = opp.get("attachment_names") or []

    if not urls:
        _update_scores(
            conn,
            opportunity_id,
            {},
            spec_text_status="no_attachment",
            spec_text_chars=0,
            spec_text_pages=0,
            spec_text_note="この案件には添付資料の登録がありません",
            scored_with_spec_text=False,
        )
        return {"id": opportunity_id, "status": "no_attachment", "score_before": score_before}

    cached = None if force else load_extraction(opportunity_id, base_dir)

    if cached is None:
        results = download_specification(opportunity_id, urls, names, base_dir=base_dir)
        documents: list[ExtractedDocument] = []
        download_errors: list[str] = []

        for result in results:
            if not result.success or not result.local_path:
                download_errors.append(f"{result.url}: {result.error}")
                continue
            documents.append(extract_pdf_text(Path(result.local_path)))

        if not documents:
            note = "添付資料をダウンロードできませんでした: " + "; ".join(download_errors[:3])
            _update_scores(
                conn,
                opportunity_id,
                {},
                spec_text_status="failed",
                spec_text_chars=0,
                spec_text_pages=0,
                spec_text_note=note,
                scored_with_spec_text=False,
            )
            return {
                "id": opportunity_id,
                "status": "download_failed",
                "score_before": score_before,
                "errors": download_errors,
            }

        save_extraction(opportunity_id, documents, base_dir)
        cached = [d.to_dict() for d in documents]

    spec_text = combined_text(cached)
    total_chars = sum(d.get("char_count", 0) for d in cached)
    total_pages = sum(d.get("page_count", 0) for d in cached)
    notes = [d["note"] for d in cached if d.get("note")]

    if total_chars == 0:
        _update_scores(
            conn,
            opportunity_id,
            {},
            spec_text_status="empty",
            spec_text_chars=0,
            spec_text_pages=total_pages,
            spec_text_note="; ".join(notes) or "テキストを抽出できませんでした(画像PDFの可能性)",
            scored_with_spec_text=False,
        )
        return {
            "id": opportunity_id,
            "status": "empty",
            "score_before": score_before,
            "pages": total_pages,
        }

    # 案件名・公告文に加えて仕様書本文も対象に再スコアリングする
    rescored = score_opportunity({**opp, "spec_text": spec_text})
    score_dict = rescored.to_db_dict()

    _update_scores(
        conn,
        opportunity_id,
        score_dict,
        spec_text_status="extracted",
        spec_text_chars=total_chars,
        spec_text_pages=total_pages,
        spec_text_note="; ".join(notes) or None,
        scored_with_spec_text=True,
    )

    return {
        "id": opportunity_id,
        "status": "extracted",
        "score_before": score_before,
        "score_after": score_dict["keyword_score"],
        "documentary_match": score_dict["documentary_match"],
        "chars": total_chars,
        "pages": total_pages,
    }


def select_targets(
    conn: sqlite3.Connection, *, min_score: int = 0, limit: int = 50, force: bool = False
) -> list[int]:
    """抽出対象の案件IDを選ぶ。既に抽出済みのものは除外する(force時を除く)。"""
    sql = """
        SELECT id FROM opportunities
        WHERE keyword_score >= ?
          AND attachment_urls IS NOT NULL
          AND attachment_urls <> '[]'
    """
    params: list[Any] = [min_score]
    if not force:
        sql += " AND spec_text_status = 'pending'"
    sql += " ORDER BY documentary_match DESC, keyword_score DESC LIMIT ?"
    params.append(limit)
    return [row["id"] for row in conn.execute(sql, params).fetchall()]
