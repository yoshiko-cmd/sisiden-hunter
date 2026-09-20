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

from src.collectors.kkj import (
    KkjApiError,
    SearchCriteria,
    build_or_query,
    build_request_params,
    collect,
    infer_organization_type,
    load_config,
    parse_response,
)
from src.database.db import get_connection, save_opportunity
from src.scoring.scorer import score_opportunity

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "kkj_sample_response.xml"
ERROR_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "kkj_error_response.xml"
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


def test_parses_multiple_attachments():
    records = {r["source_key"]: r for r in collect(live=False, fixture_path=FIXTURE_PATH)}

    multi = records["KKJ-TEST-0002"]
    assert len(multi["attachment_urls"]) == 3, "<Attachments>内の複数<Attachment>を全て拾うこと"
    assert multi["attachment_names"][0] == "公募要項"
    assert multi["attachment_urls"][0].endswith("youkou.pdf")

    # Attachmentsタグ自体が無い案件(オプション項目の欠落)
    assert records["KKJ-TEST-0003"]["attachment_urls"] == []


def test_optional_tags_missing_is_tolerated():
    """オプション項目はタグ自体が出力されないことがある(APIガイド4.2)。"""
    records = {r["source_key"]: r for r in collect(live=False, fixture_path=FIXTURE_PATH)}

    national = records["KKJ-TEST-0007"]  # PrefectureName/CityName/Location無し
    assert national["prefecture"] is None
    assert national["municipality"] is None
    assert national["location"] is None
    assert national["project_name"] == "全国中小企業実態調査業務"


def test_organization_type_inference():
    records = {r["source_key"]: r for r in collect(live=False, fixture_path=FIXTURE_PATH)}

    assert records["KKJ-TEST-0001"]["organization_type"] == "都道府県"
    assert records["KKJ-TEST-0006"]["organization_type"] == "市区町村"
    assert records["KKJ-TEST-0007"]["organization_type"] == "独立行政法人等"
    assert infer_organization_type("総務省", None, None) == "国"


def test_error_response_raises():
    """<Results><Error>...</Error></Results> はKkjApiErrorとして扱う(APIガイド5章)。"""
    error_xml = ERROR_FIXTURE_PATH.read_text(encoding="utf-8")
    try:
        parse_response(error_xml)
    except KkjApiError as exc:
        assert "Invalid Date Parameter" in str(exc)
    else:
        raise AssertionError("エラー応答でKkjApiErrorが投げられていない")


def test_request_params_match_api_guide():
    config = load_config()

    params = build_request_params(
        SearchCriteria(query="動画", published_from="2026-09-01", published_to="2026-09-30"), config
    )
    assert params["Query"] == "動画"
    assert params["CFT_Issue_Date"] == "2026-09-01/2026-09-30"

    # 「開始日/」形式(終了日なし)
    params = build_request_params(SearchCriteria(query="映像", published_from="2026-09-01"), config)
    assert params["CFT_Issue_Date"] == "2026-09-01/"

    # 「開始終了日」形式(同日指定)、都道府県コードは複数をカンマ区切りで送信
    params = build_request_params(
        SearchCriteria(
            lg_codes=["01", "13"], published_from="2026-09-01", published_to="2026-09-01"
        ),
        config,
    )
    assert params["CFT_Issue_Date"] == "2026-09-01"
    assert params["LG_Code"] == "01,13"

    # 必須パラメータ未指定はエラー
    try:
        build_request_params(SearchCriteria(published_from="2026-09-01"), config)
    except ValueError:
        pass
    else:
        raise AssertionError("必須パラメータ未指定でValueErrorが投げられていない")


def test_count_is_always_sent():
    """Countは未指定だとデフォルト10件しか返らないため、必ず送る必要がある(APIガイド3章)。"""
    config = load_config()

    params = build_request_params(SearchCriteria(query="動画"), config)
    assert params["Count"] == "1000", "Count未指定時はdefault_countを送ること"

    # 上限1,000を超える指定は1,000に丸める
    params = build_request_params(SearchCriteria(query="動画", count=5000), config)
    assert params["Count"] == "1000"

    params = build_request_params(SearchCriteria(query="動画", count=50), config)
    assert params["Count"] == "50"


def test_or_query_syntax():
    """OR検索式は演算子の前後に半角空白が必要(APIガイド3.1)。"""
    assert build_or_query(["映像", "動画"]) == "映像 OR 動画"
    assert build_or_query(["映像", "", "動画"]) == "映像 OR 動画"
    # 空白を含む語は()で優先順位を明示する
    assert build_or_query(["SNS 動画", "映像"]) == "(SNS 動画) OR 映像"


def test_prefecture_codes_cover_all_47():
    config = load_config()
    codes = config["prefecture_codes"]
    assert len(codes) == 47
    assert codes["01"] == "北海道"
    assert codes["47"] == "沖縄県"
    assert all(len(str(c)) == 2 for c in codes), "都道府県コードは先行ゼロを含む2桁"


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
