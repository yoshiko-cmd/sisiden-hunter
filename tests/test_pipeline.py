"""パイプライン全体(収集→重複排除→スコアリング→DB→MCPツール)の自動テスト。

実行方法: python3 -m pytest tests/ -v (要 pytest)
または:  python3 tests/test_pipeline.py (pytest無しでも直接実行可)
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.collectors.kkj import collect
from src.database.db import get_connection, save_opportunity
from src.scoring.scorer import score_opportunity

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "kkj_sample_response.xml"
SCHEMA_PATH = ROOT / "src" / "database" / "schema.sql"


def _make_temp_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp())
    db_path = tmp_dir / "test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return db_path


def test_collect_fixture_returns_10_records():
    records = collect(live=False, fixture_path=FIXTURE_PATH)
    assert len(records) == 10
    assert records[0]["source_key"] == "KKJ-TEST-0001"


def test_scoring_prioritizes_documentary_over_plain_video():
    records = {r["source_key"]: r for r in collect(live=False, fixture_path=FIXTURE_PATH)}

    documentary_score = score_opportunity(records["KKJ-TEST-0002"]).keyword_score  # ドキュメンタリー職人密着
    plain_pr_score = score_opportunity(records["KKJ-TEST-0008"]).keyword_score      # 観光PR動画のみ
    noise_score = score_opportunity(records["KKJ-TEST-0003"]).keyword_score         # 議会中継(除外対象)

    assert documentary_score > plain_pr_score, "ドキュメンタリー案件は単純PR動画より高スコアであるべき"
    assert noise_score == 0, "議会中継のみの案件はスコア0であるべき"


def test_dedup_prevents_double_insertion():
    db_path = _make_temp_db()
    conn = get_connection(db_path)
    records = collect(live=False, fixture_path=FIXTURE_PATH)

    new_count_1 = sum(save_opportunity(conn, r, score_opportunity(r).to_db_dict())[0] for r in records)
    new_count_2 = sum(save_opportunity(conn, r, score_opportunity(r).to_db_dict())[0] for r in records)

    total_rows = conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0]
    conn.close()

    assert new_count_1 == 10, "初回投入はすべて新規のはず"
    assert new_count_2 == 0, "2回目投入は全件重複のはず"
    assert total_rows == 10, "DB行数は10件のまま増えないはず"


def test_mcp_tools_end_to_end():
    async def _run():
        db_path = _make_temp_db()
        conn = get_connection(db_path)
        for r in collect(live=False, fixture_path=FIXTURE_PATH):
            save_opportunity(conn, r, score_opportunity(r).to_db_dict())
        conn.close()

        from src.mcp import tools

        search_result = tools.search_opportunities(documentary_only=True, db_path=str(db_path))
        assert search_result["count"] >= 1
        first_id = search_result["results"][0]["id"]

        detail = tools.get_opportunity(first_id, db_path=str(db_path))
        assert detail["found"] is True

        updated = tools.update_opportunity_status(
            first_id, status="candidate", memo="テストメモ", db_path=str(db_path)
        )
        assert updated["opportunity"]["status"] == "candidate"
        assert updated["opportunity"]["memo"] == "テストメモ"

        not_found = tools.get_opportunity(99999, db_path=str(db_path))
        assert not_found["found"] is False

        invalid_status = tools.update_opportunity_status(first_id, status="bogus", db_path=str(db_path))
        assert invalid_status["found"] is False

        ranking = tools.list_top_opportunities(limit=5, db_path=str(db_path))
        assert ranking["count"] > 0
        assert ranking["results"][0]["documentary_match"] == 1

    asyncio.run(_run())


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")


if __name__ == "__main__":
    _run_all()
