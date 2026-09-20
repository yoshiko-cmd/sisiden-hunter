#!/usr/bin/env python3
"""案件収集の実行スクリプト(要件5,33)。

使い方:
    python scripts/collect.py --live --query 動画          # 実API呼び出し
    python scripts/collect.py --fixture tests/fixtures/kkj_sample_response.xml  # オフラインテスト

新規案件をDBへ保存し、重複は登録しない。処理結果はcollection_logsテーブルと
標準出力にログとして記録する(取得件数/新規/重複/エラー/処理時間)。
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collectors.kkj import KkjApiError, SearchCriteria, collect as kkj_collect
from src.database.db import (
    DEFAULT_DB_PATH,
    finish_collection_log,
    get_connection,
    save_opportunity,
    start_collection_log,
)
from src.scoring.scorer import score_opportunity

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sisiden.collect")


def run(
    *,
    live: bool,
    fixture_path: Path | None,
    query: str | None,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    conn = get_connection(db_path)
    log_id = start_collection_log(conn, source="kkj", started_at=started.isoformat())

    fetched_count = 0
    new_count = 0
    duplicate_count = 0
    error_count = 0

    try:
        criteria = SearchCriteria(query=query) if query else SearchCriteria(query="動画")
        records = kkj_collect(criteria, live=live, fixture_path=fixture_path)
        fetched_count = len(records)
        logger.info("取得 %d件", fetched_count)

        for record in records:
            try:
                score = score_opportunity(record).to_db_dict()
                is_new, opp_id = save_opportunity(conn, record, score)
                if is_new:
                    new_count += 1
                    logger.info("新規登録 id=%s score=%s %s", opp_id, score["keyword_score"], record.get("project_name"))
                else:
                    duplicate_count += 1
            except Exception:  # noqa: BLE001 - 1件のエラーで全体を止めない(要件34)
                error_count += 1
                logger.exception("案件の保存に失敗しました: %s", record.get("source_key"))
    except KkjApiError as exc:
        error_count += 1
        logger.error("API接続エラー: %s", exc)
    finally:
        duration = time.monotonic() - t0
        finish_collection_log(
            conn,
            log_id,
            finished_at=datetime.now(timezone.utc).isoformat(),
            fetched_count=fetched_count,
            new_count=new_count,
            duplicate_count=duplicate_count,
            error_count=error_count,
            duration_seconds=duration,
            note="live" if live else f"fixture:{fixture_path}",
        )
        conn.close()

    summary = {
        "fetched_count": fetched_count,
        "new_count": new_count,
        "duplicate_count": duplicate_count,
        "error_count": error_count,
        "duration_seconds": round(duration, 2),
    }
    logger.info(
        "収集完了: 取得%(fetched_count)d件 新規%(new_count)d件 重複%(duplicate_count)d件 "
        "エラー%(error_count)d件 処理時間%(duration_seconds).2f秒",
        summary,
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="官公需情報ポータルサイトから案件を収集する")
    parser.add_argument("--live", action="store_true", help="実APIへ接続する")
    parser.add_argument("--fixture", type=str, help="オフラインテスト用のフィクスチャXMLパス")
    parser.add_argument("--query", type=str, help="検索キーワード(Queryパラメータ)")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="DBファイルパス")
    args = parser.parse_args()

    if not args.live and not args.fixture:
        parser.error("--live または --fixture のいずれかを指定してください")

    run(
        live=args.live,
        fixture_path=Path(args.fixture) if args.fixture else None,
        query=args.query,
        db_path=Path(args.db),
    )


if __name__ == "__main__":
    main()
