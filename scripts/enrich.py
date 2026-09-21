#!/usr/bin/env python3
"""候補案件の仕様書PDFを取得・抽出し、本文を含めて再スコアリングする。

「案件名には書かれていないが、仕様書にドキュメンタリーと書いてある案件」を拾うための処理。
すべてローカル処理(pypdf)で完結し、LLM APIは使用しない。

使い方:
    python scripts/enrich.py                 # 未抽出かつ添付ありの案件を最大50件処理
    python scripts/enrich.py --min-score 25  # スコア25点以上に限定
    python scripts/enrich.py --id 12         # 特定案件のみ
    python scripts/enrich.py --id 12 --force # 抽出済みでも再取得する
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.attachments.enrich import enrich_opportunity, select_targets
from src.database.db import DEFAULT_DB_PATH, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sisiden.enrich")


def main() -> int:
    parser = argparse.ArgumentParser(description="仕様書PDFを取得・抽出して再スコアリングする")
    parser.add_argument("--id", type=int, help="対象案件ID(未指定なら条件に合う案件を一括処理)")
    parser.add_argument("--min-score", type=int, default=0, help="対象とする最低スコア")
    parser.add_argument("--limit", type=int, default=50, help="一括処理の最大件数")
    parser.add_argument("--force", action="store_true", help="抽出済みでも再取得する")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="DBファイルパス")
    args = parser.parse_args()

    conn = get_connection(Path(args.db))
    try:
        targets = [args.id] if args.id else select_targets(
            conn, min_score=args.min_score, limit=args.limit, force=args.force
        )
        if not targets:
            logger.info("対象案件がありません")
            return 0

        logger.info("対象 %d件", len(targets))
        stats = {"extracted": 0, "empty": 0, "no_attachment": 0, "download_failed": 0, "not_found": 0}
        upgraded = 0

        for opportunity_id in targets:
            result = enrich_opportunity(conn, opportunity_id, force=args.force)
            stats[result["status"]] = stats.get(result["status"], 0) + 1

            if result["status"] == "extracted":
                before, after = result["score_before"], result["score_after"]
                changed = after != before
                if changed:
                    upgraded += 1
                logger.info(
                    "id=%s %s %d頁 %d文字 スコア %d→%d%s",
                    opportunity_id,
                    "★スコア変動" if changed else "変動なし",
                    result["pages"],
                    result["chars"],
                    before,
                    after,
                    " (ドキュメンタリー検出)" if result["documentary_match"] else "",
                )
            else:
                # 失敗した場合は理由まで表示する(原因調査のため)
                detail = result.get("note") or ""
                files = result.get("files")
                if files:
                    detail = f"{detail} [{', '.join(str(f) for f in files[:2])}]"
                logger.info("id=%s %s %s", opportunity_id, result["status"], detail.strip())

        logger.info(
            "完了: 抽出%d件 / PDF以外%d件 テキスト無し(画像PDF等)%d件 "
            "解析失敗%d件 添付無し%d件 DL失敗%d件 / スコア変動%d件",
            stats.get("extracted", 0),
            stats.get("not_pdf", 0),
            stats.get("empty", 0),
            stats.get("failed", 0),
            stats.get("no_attachment", 0),
            stats.get("download_failed", 0),
            upgraded,
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
