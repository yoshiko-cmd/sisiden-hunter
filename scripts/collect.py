#!/usr/bin/env python3
"""案件収集の実行スクリプト(要件5,33)。

使い方:
    python scripts/collect.py --live                  # 映像・ドキュメンタリー系キーワードで全国収集
    python scripts/collect.py --live --query 動画     # 単一キーワードで収集
    python scripts/collect.py --live --days 30        # 直近30日の公告に限定
    python scripts/collect.py --fixture tests/fixtures/kkj_sample_response.xml  # オフライン検証

APIはLG_Code未指定時に全国を対象とするため、キーワードを変えて複数回呼び出すことで
全国の案件を収集する。新規案件のみDBへ保存し、重複は登録しない。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collectors.kkj import (
    KkjApiError,
    SearchCriteria,
    collect as kkj_collect,
    collect_by_prefecture,
    collect_tiers,
)
from src.database.db import (
    DEFAULT_DB_PATH,
    finish_collection_log,
    get_connection,
    get_opportunity_by_id,
    save_opportunity,
    start_collection_log,
)
from src.notify.discord import post_opportunities, select_notifiable
from src.scoring.scorer import score_opportunity

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sisiden.collect")

JST = timezone(timedelta(hours=9))


def _parse_tiers(value: str | None) -> list[str] | None:
    """--tiers "A,B" 形式の指定を解釈する。未指定なら全階層。"""
    if not value:
        return None
    return [t.strip().upper() for t in value.split(",") if t.strip()]


def run(
    *,
    live: bool,
    fixture_path: Path | None,
    query: str | None,
    days: int | None,
    by_prefecture: bool = False,
    tiers: list[str] | None = None,
    notify: bool = True,
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
    new_ids: list[int] = []
    note_parts: list[str] = []

    published_from = None
    if days:
        published_from = (datetime.now(JST) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        if not live:
            records = kkj_collect(live=False, fixture_path=fixture_path)
            note_parts.append(f"fixture:{fixture_path}")
        elif query:
            criteria = SearchCriteria(query=query, published_from=published_from)
            records = kkj_collect(criteria, live=True)
            note_parts.append(f"live:query={query}")
        elif by_prefecture:
            records, errors = collect_by_prefecture(published_from=published_from, tiers=tiers)
            error_count += len(errors)
            note_parts.append("live:tiers:by-prefecture")
            if errors:
                note_parts.append(f"errors={len(errors)}")
        else:
            records, errors, tier_stats = collect_tiers(published_from=published_from, tiers=tiers)
            error_count += len(errors)
            note_parts.append(
                "live:tiers:" + ",".join(f"{k}={v}" for k, v in tier_stats.items())
            )
            if errors:
                note_parts.append(f"errors={len(errors)}")

        fetched_count = len(records)
        logger.info("取得 %d件", fetched_count)

        for record in records:
            try:
                score = score_opportunity(record).to_db_dict()
                is_new, opp_id = save_opportunity(conn, record, score)
                if is_new:
                    new_count += 1
                    new_ids.append(opp_id)
                    logger.info(
                        "新規登録 id=%s score=%s %s", opp_id, score["keyword_score"], record.get("project_name")
                    )
                else:
                    duplicate_count += 1
            except Exception:  # noqa: BLE001 - 1件のエラーで全体を止めない(要件34)
                error_count += 1
                logger.exception("案件の保存に失敗しました: %s", record.get("source_key"))
        # 新規登録された案件のうち、条件を満たすものをDiscordへ通知する。
        # 通知の失敗で収集処理を止めない(要件34)。
        if new_ids and notify:
            try:
                new_records = [
                    opp for opp in (get_opportunity_by_id(conn, i) for i in new_ids) if opp
                ]
                targets = select_notifiable(new_records)
                if targets:
                    post_opportunities(
                        targets,
                        summary=f"**新着案件 {len(targets)}件**(収集{fetched_count}件中 新規{new_count}件)",
                    )
            except Exception:  # noqa: BLE001 - 通知は付随機能のため全体を止めない
                logger.exception("Discord通知に失敗しました")
    except (KkjApiError, ValueError) as exc:
        error_count += 1
        logger.error("収集エラー: %s", exc)
        note_parts.append(f"fatal:{exc}")
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
            note=" ".join(note_parts),
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


def main() -> int:
    """CLIエントリポイント。cron等から定期実行できるよう終了コードを返す。

    スケジューラ固有の処理はここには書かない(deploy/ に設定例を置く)。
    終了コード: 0=正常, 1=エラーあり, 2=多重起動を検知して中断
    """
    parser = argparse.ArgumentParser(description="官公需情報ポータルサイトから案件を収集する")
    parser.add_argument("--live", action="store_true", help="実APIへ接続する")
    parser.add_argument("--fixture", type=str, help="オフライン検証用のフィクスチャXMLパス")
    parser.add_argument("--query", type=str, help="検索式を直接指定する(未指定なら3階層収集)")
    parser.add_argument("--days", type=int, help="直近N日の公告に限定する")
    parser.add_argument("--tiers", type=str, help="収集する階層(例: A,B)。未指定なら全階層")
    parser.add_argument(
        "--by-prefecture",
        action="store_true",
        help="47都道府県を1つずつ収集する(1リクエスト1,000件の上限対策)",
    )
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="DBファイルパス")
    parser.add_argument("--no-notify", action="store_true", help="Discordへの新着通知を行わない")
    parser.add_argument("--log-file", type=str, help="ログの出力先ファイル(cron実行時に指定)")
    parser.add_argument("--lock-file", type=str, help="多重起動防止用のロックファイル")
    args = parser.parse_args()

    if not args.live and not args.fixture:
        parser.error("--live または --fixture のいずれかを指定してください")

    if args.log_file:
        handler = logging.FileHandler(args.log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)

    lock_path = Path(args.lock_file) if args.lock_file else None
    if lock_path:
        try:
            # O_EXCLで原子的に作成。既に存在する場合は前回実行が進行中とみなす。
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
        except FileExistsError:
            logger.error("ロックファイルが存在します(前回の実行が進行中の可能性): %s", lock_path)
            return 2

    try:
        summary = run(
            live=args.live,
            fixture_path=Path(args.fixture) if args.fixture else None,
            query=args.query,
            days=args.days,
            by_prefecture=args.by_prefecture,
            tiers=_parse_tiers(args.tiers),
            notify=not args.no_notify,
            db_path=Path(args.db),
        )
    finally:
        if lock_path:
            lock_path.unlink(missing_ok=True)

    return 1 if summary["error_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
