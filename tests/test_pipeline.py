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
    build_tier_queries,
    collect,
    infer_organization_type,
    load_collection_queries,
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


def test_tier_queries_are_built_per_api_syntax():
    """3階層の検索式を組み立てる(APIガイド3.1の検索式構文)。"""
    queries_config = load_collection_queries()
    tiers = queries_config["tiers"]

    # A/BはそのままOR検索式
    a_queries = build_tier_queries(tiers["A"])
    assert len(a_queries) >= 1
    assert "ドキュメンタリー" in " ".join(a_queries)
    assert " OR " in a_queries[0]
    assert " AND " not in a_queries[0], "standalone階層にANDは入らない"

    b_queries = build_tier_queries(tiers["B"])
    assert "シティプロモーション" in " ".join(b_queries)

    # Cはテーマ語を発信系の語とAND結合する(単独では大量取得になるため)
    c_queries = build_tier_queries(tiers["C"])
    assert all(" AND " in q for q in c_queries), "combined階層は必ずANDで結合する"
    for q in c_queries:
        theme_part, modifier_part = q.split(" AND ", 1)
        # 優先順位が左から評価されるため、両側を括弧で囲む必要がある
        assert theme_part.startswith("(") and theme_part.endswith(")")
        assert modifier_part.startswith("(") and modifier_part.endswith(")")
    joined = " ".join(c_queries)
    assert "社会課題" in joined and "産学連携" in joined

    # combinedなのにmodifiersが無い定義はエラー
    try:
        build_tier_queries({"mode": "combined", "words": ["若者"]})
    except ValueError:
        pass
    else:
        raise AssertionError("modifiers無しのcombined階層でValueErrorが投げられていない")


def test_api_tender_date_is_not_treated_as_application_deadline():
    """TenderSubmissionDeadlineは応募締切と決めつけない(APIガイド上は入札開始日)。"""
    records = {r["source_key"]: r for r in collect(live=False, fixture_path=FIXTURE_PATH)}
    record = records["KKJ-TEST-0001"]

    assert record["api_tender_date"] == "2026-10-10"
    assert "deadline" not in record, "APIの値をdeadlineという名前で持たない"

    db_path = _make_temp_db()
    conn = get_connection(db_path)
    save_opportunity(conn, record, score_opportunity(record).to_db_dict())
    row = conn.execute(
        "SELECT api_tender_date, application_deadline, deadline_verified FROM opportunities"
    ).fetchone()
    assert row["api_tender_date"] == "2026-10-10"
    assert row["application_deadline"] is None, "確認前の応募締切は空のまま"
    assert row["deadline_verified"] == 0

    # 仕様書で確認した締切を記録すると、確認済みフラグが立つ
    from src.mcp import tools

    conn.close()
    updated = tools.update_opportunity_status(
        1,
        application_deadline="2026-10-03",
        deadline_source="仕様書 p.3 企画提案書提出期限",
        db_path=str(db_path),
    )
    assert updated["opportunity"]["application_deadline"] == "2026-10-03"
    assert updated["opportunity"]["deadline_verified"] == 1

    # 検索の締切条件は確認済みの応募締切を優先して評価する
    hit = tools.search_opportunities(deadline_to="2026-10-05", db_path=str(db_path))
    assert hit["count"] == 1, "application_deadline(10/03)で絞り込めること"
    miss = tools.search_opportunities(deadline_from="2026-10-08", db_path=str(db_path))
    assert miss["count"] == 0, "api_tender_date(10/10)ではなく応募締切で判定すること"


def _write_test_pdf(path: Path, pages: list[str]) -> None:
    """日本語テキストを埋め込んだPDFを生成する(pypdfの抽出を実際に検証するため)。

    行政の公告PDFに近い形を再現するため、日本語CIDフォントを埋め込む。
    reportlabはテスト専用の依存(requirements-dev.txt)。
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    c = canvas.Canvas(str(path), pagesize=A4)
    for text in pages:
        c.setFont("HeiseiKakuGo-W5", 11)
        y = 780
        # 長い行は折り返して描画する
        for i in range(0, len(text), 40):
            c.drawString(50, y, text[i : i + 40])
            y -= 18
        c.showPage()
    c.save()


def test_pdf_text_extraction_finds_documentary_in_spec():
    """案件名に無くても仕様書本文にドキュメンタリー記述があれば検出できること。"""
    import tempfile

    from src.attachments.extractor import extract_pdf_text

    tmp_dir = Path(tempfile.mkdtemp())
    pdf_path = tmp_dir / "spec.pdf"
    _write_test_pdf(
        pdf_path,
        [
            "1 業務名 地域資源活用事業に係る記録業務",
            "2 業務内容 事業者への密着取材を行いドキュメンタリー形式で記録すること",
        ],
    )

    doc = extract_pdf_text(pdf_path)
    assert doc.status == "extracted", f"抽出に失敗: {doc.note}"
    assert doc.page_count == 2
    assert "ドキュメンタリー" in "".join(doc.pages)

    # 案件名・公告文だけではドキュメンタリー判定されないが、仕様書本文を加えると検出される
    record = {"project_name": "地域資源活用事業に係る記録業務", "description": "記録業務一式"}
    assert score_opportunity(record).matches["documentary_match"] is False

    with_spec = score_opportunity({**record, "spec_text": "".join(doc.pages)})
    assert with_spec.matches["documentary_match"] is True
    assert with_spec.keyword_score > score_opportunity(record).keyword_score


def test_extractor_reports_image_only_pdf_honestly():
    """テキストが埋め込まれていないPDFは、できたことにせずemptyとして記録する。"""
    import tempfile

    from pypdf import PdfWriter

    from src.attachments.extractor import extract_pdf_text

    tmp_dir = Path(tempfile.mkdtemp())
    pdf_path = tmp_dir / "image_only.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    doc = extract_pdf_text(pdf_path)
    assert doc.status == "empty"
    assert doc.char_count == 0
    assert "画像スキャン" in (doc.note or "")


def test_enrich_records_failure_without_crashing():
    """添付をダウンロードできない場合も、落ちずに理由を記録すること(要件34)。"""
    from src.attachments.enrich import enrich_opportunity

    db_path = _make_temp_db()
    conn = get_connection(db_path)
    records = {r["source_key"]: r for r in collect(live=False, fixture_path=FIXTURE_PATH)}

    # 添付あり(到達不能なURL)
    with_attachment = records["KKJ-TEST-0001"]
    save_opportunity(conn, with_attachment, score_opportunity(with_attachment).to_db_dict())
    # 添付なし
    without_attachment = records["KKJ-TEST-0003"]
    save_opportunity(conn, without_attachment, score_opportunity(without_attachment).to_db_dict())

    failed = enrich_opportunity(conn, 1)
    assert failed["status"] == "download_failed"

    none_result = enrich_opportunity(conn, 2)
    assert none_result["status"] == "no_attachment"

    rows = {
        r["id"]: r["spec_text_status"]
        for r in conn.execute("SELECT id, spec_text_status FROM opportunities")
    }
    assert rows[1] == "failed"
    assert rows[2] == "no_attachment"

    missing = enrich_opportunity(conn, 9999)
    assert missing["status"] == "not_found"
    conn.close()


def test_get_specification_text_paginates():
    """仕様書テキストは全文を一度に返さず、ページ範囲で読み進められること。"""
    import tempfile

    from src.attachments.extractor import extract_pdf_text, save_extraction
    from src.mcp import tools

    db_path = _make_temp_db()
    conn = get_connection(db_path)
    records = collect(live=False, fixture_path=FIXTURE_PATH)
    for r in records:
        save_opportunity(conn, r, score_opportunity(r).to_db_dict())
    conn.close()

    # 抽出済みキャッシュを用意し、ダウンロードなしでツールの挙動を検証する
    base_dir = Path(tempfile.mkdtemp())
    pdf_path = base_dir / "spec.pdf"
    _write_test_pdf(pdf_path, [f"{i}ページ目の仕様書本文です。" * 40 for i in range(1, 6)])
    save_extraction(1, [extract_pdf_text(pdf_path)], base_dir)

    import src.mcp.tools as tools_module

    original = tools_module.load_extraction
    tools_module.load_extraction = lambda opportunity_id: original(opportunity_id, base_dir)
    try:
        first = tools.get_specification_text(1, max_chars=500, db_path=str(db_path))
        assert first["extracted"] is True
        assert first["total_pages"] == 5
        assert len(first["text"]) <= 500, "max_charsを超えて返さない"
        assert first["has_more"] is True
        assert first["next_page_from"] == first["page_to"] + 1

        # 続きを読む
        second = tools.get_specification_text(
            1, page_from=first["next_page_from"], max_chars=500, db_path=str(db_path)
        )
        assert second["page_from"] == first["next_page_from"]
        assert second["text"] != first["text"]

        # 範囲外の指定はエラーとして返す(例外にしない)
        out_of_range = tools.get_specification_text(1, page_from=99, db_path=str(db_path))
        assert "error" in out_of_range

        bad_index = tools.get_specification_text(1, attachment_index=5, db_path=str(db_path))
        assert "error" in bad_index
    finally:
        tools_module.load_extraction = original


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")


if __name__ == "__main__":
    _run_all()
