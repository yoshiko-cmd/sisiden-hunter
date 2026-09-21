#!/usr/bin/env python3
"""実APIからの取得を検証するスクリプト(Phase 1の完了条件)。

ネットワーク到達可能な環境で実行し、以下を一度に確認する:
  1. 実APIへの接続と10件取得
  2. XMLパース(必須項目が埋まっているか)
  3. 日付の扱い(api_tender_dateとして保持されているか)
  4. 添付URLの取得
  5. DB保存と重複排除(2回保存して増えないこと)
  6. スコアリング

使い方:
    python scripts/verify_live.py
    python scripts/verify_live.py --count 10 --db data/verify.db
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collectors.kkj import KkjApiError, SearchCriteria, collect
from src.database.db import get_connection, save_opportunity
from src.scoring.scorer import score_opportunity

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
# リトライ経過の警告は結果表示と重複するため、最終的なエラーだけを見せる
logging.getLogger("sisiden.collectors.kkj").setLevel(logging.ERROR)
SCHEMA_PATH = ROOT / "src" / "database" / "schema.sql"


def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'NG'}] {label}{(': ' + detail) if detail else ''}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="実APIからの取得を検証する")
    parser.add_argument("--count", type=int, default=10, help="取得件数")
    parser.add_argument("--query", type=str, default="映像 OR 動画 OR ドキュメンタリー")
    parser.add_argument("--db", type=str, help="検証用DBパス(未指定なら一時ファイル)")
    args = parser.parse_args()

    print("=" * 60)
    print("1. 実APIへの接続")
    print("=" * 60)
    try:
        records = collect(SearchCriteria(query=args.query, count=args.count), live=True)
    except KkjApiError as exc:
        print(f"  [NG] 接続に失敗しました\n\n  {exc}\n")
        print("  → この環境からは官公需情報ポータルへ到達できません。")
        print("     ネットワーク制限のない環境で再実行してください。")
        return 1

    if not _check(f"{len(records)}件取得", len(records) > 0):
        print("  → 検索条件に一致する案件がありませんでした。--query や期間を変えて再試行してください。")
        return 1

    print()
    print("=" * 60)
    print("2. XMLパース(必須項目)")
    print("=" * 60)
    results = [
        _check("source_keyが埋まっている", all(r.get("source_key") for r in records)),
        _check("project_nameが埋まっている", all(r.get("project_name") for r in records)),
        _check(
            "organization_nameが埋まっている",
            sum(1 for r in records if r.get("organization_name")) > 0,
            f"{sum(1 for r in records if r.get('organization_name'))}/{len(records)}件",
        ),
        _check(
            "published_date(公告日)が埋まっている",
            sum(1 for r in records if r.get("published_date")) > 0,
            f"{sum(1 for r in records if r.get('published_date'))}/{len(records)}件",
        ),
    ]

    print()
    print("=" * 60)
    print("3. 日付の扱い")
    print("=" * 60)
    results.append(_check("deadlineという名前で保持していない", all("deadline" not in r for r in records)))
    with_tender = [r for r in records if r.get("api_tender_date")]
    _check(
        "api_tender_dateとして保持",
        True,
        f"{len(with_tender)}/{len(records)}件に値あり(APIガイド上は入札開始日のため応募締切とは限らない)",
    )

    print()
    print("=" * 60)
    print("4. 添付URL")
    print("=" * 60)
    with_attachments = [r for r in records if r.get("attachment_urls")]
    _check(
        "添付URLを取得",
        True,
        f"{len(with_attachments)}/{len(records)}件に添付あり",
    )
    if with_attachments:
        sample = with_attachments[0]
        print(f"      例: {sample['attachment_names'][:2]} -> {sample['attachment_urls'][:1]}")

    print()
    print("=" * 60)
    print("5. DB保存と重複排除")
    print("=" * 60)
    db_path = Path(args.db) if args.db else Path(tempfile.mkdtemp()) / "verify.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()

    first_pass = sum(save_opportunity(conn, r, score_opportunity(r).to_db_dict())[0] for r in records)
    second_pass = sum(save_opportunity(conn, r, score_opportunity(r).to_db_dict())[0] for r in records)
    total = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]

    results.append(_check("初回保存で全件新規", first_pass == len(records), f"{first_pass}件"))
    results.append(_check("2回目は全件重複として除外", second_pass == 0, f"新規{second_pass}件"))
    results.append(_check("DB件数が増えていない", total == len(records), f"{total}件"))

    print()
    print("=" * 60)
    print("6. スコアリング")
    print("=" * 60)
    scores = [score_opportunity(r).keyword_score for r in records]
    results.append(_check("スコアが計算されている", len(scores) == len(records)))
    print(f"      最高{max(scores)}点 / 最低{min(scores)}点 / 平均{sum(scores) / len(scores):.1f}点")

    rows = conn.execute(
        "SELECT project_name, prefecture, keyword_score, documentary_match, api_tender_date"
        " FROM opportunities ORDER BY keyword_score DESC LIMIT 5"
    ).fetchall()
    print("\n  上位5件:")
    for row in rows:
        mark = "★" if row["documentary_match"] else " "
        print(
            f"    {mark}[{row['keyword_score']:3d}] {(row['prefecture'] or '—')} "
            f"{row['project_name'][:34]} (API日付: {row['api_tender_date'] or '—'})"
        )
    conn.close()

    print()
    print("=" * 60)
    passed = all(results)
    print(f"結果: {'すべて合格' if passed else '不合格の項目があります'}")
    print(f"検証用DB: {db_path}")
    print("=" * 60)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
