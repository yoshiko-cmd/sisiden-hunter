#!/usr/bin/env python3
"""DBに保存済みの案件を、現在のキーワード設定で採点し直す。

config/keywords.yaml を調整したあとに実行する。再収集は不要。
抽出済みの仕様書本文があれば、それも採点対象に含める。

使い方:
    python scripts/rescore.py                 # 全件を採点し直す
    python scripts/rescore.py --dry-run       # 変更内容だけ表示して保存しない
    python scripts/rescore.py --show 20       # 採点後の上位20件を表示
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.attachments.extractor import combined_text, load_extraction
from src.database.db import DEFAULT_DB_PATH, get_connection

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("sisiden.rescore")

SCORE_COLUMNS = [
    "video_match", "documentary_match", "social_issue_match", "local_industry_match",
    "youth_match", "community_match", "education_match",
    "human_story_candidate", "project_story_candidate", "keyword_score",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="保存済み案件を現在の設定で採点し直す")
    parser.add_argument("--dry-run", action="store_true", help="保存せず変更内容だけ表示する")
    parser.add_argument("--show", type=int, default=15, help="採点後に表示する上位件数")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="DBファイルパス")
    args = parser.parse_args()

    # keywords.yamlの変更を確実に読み直す
    from src.scoring.keywords import load_keywords
    from src.scoring.scorer import score_opportunity

    load_keywords(force_reload=True)

    conn = get_connection(Path(args.db))
    try:
        rows = conn.execute(
            "SELECT id, project_name, description, category, procedure_type,"
            " keyword_score, spec_text_status FROM opportunities"
        ).fetchall()
        if not rows:
            logger.info("案件がありません。先に collect.py を実行してください。")
            return 0

        logger.info("%d件を採点し直します...", len(rows))
        changed = 0
        raised = 0
        lowered = 0

        for row in rows:
            record = dict(row)
            # 仕様書本文を抽出済みなら採点対象に含める
            if row["spec_text_status"] == "extracted":
                documents = load_extraction(row["id"])
                if documents:
                    record["spec_text"] = combined_text(documents)

            result = score_opportunity(record)
            new_score = result.keyword_score
            old_score = row["keyword_score"]

            if new_score != old_score:
                changed += 1
                if new_score > old_score:
                    raised += 1
                else:
                    lowered += 1

            if not args.dry_run:
                score = result.to_db_dict()
                assignments = ", ".join(f"{c} = ?" for c in SCORE_COLUMNS)
                conn.execute(
                    f"UPDATE opportunities SET {assignments}, updated_at = datetime('now') WHERE id = ?",
                    [*[score[c] for c in SCORE_COLUMNS], row["id"]],
                )

        if not args.dry_run:
            conn.commit()

        logger.info(
            "変更 %d件 (上昇%d / 下降%d) %s",
            changed,
            raised,
            lowered,
            "※dry-runのため保存していません" if args.dry_run else "",
        )

        if args.show:
            logger.info("")
            logger.info("=== 採点後の上位%d件 ===", args.show)
            top = conn.execute(
                "SELECT id, project_name, prefecture, keyword_score, documentary_match,"
                " human_story_candidate FROM opportunities"
                " ORDER BY documentary_match DESC, keyword_score DESC LIMIT ?",
                (args.show,),
            ).fetchall()
            for r in top:
                mark = "★" if r["documentary_match"] else " "
                person = "[人]" if r["human_story_candidate"] else "   "
                pref = r["prefecture"] or "—"
                logger.info(
                    "%s[%3d]%s %s %s", mark, r["keyword_score"], person, pref, r["project_name"][:44]
                )

            total = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
            with_score = conn.execute(
                "SELECT COUNT(*) FROM opportunities WHERE keyword_score > 0"
            ).fetchone()[0]
            high = conn.execute(
                "SELECT COUNT(*) FROM opportunities WHERE keyword_score >= 50"
            ).fetchone()[0]
            logger.info("")
            logger.info("全%d件中 スコア1点以上:%d件 / 50点以上:%d件", total, with_score, high)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
