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


def test_construction_work_is_not_scored_as_video():
    """実データで発生した誤判定の回帰テスト。

    実際の890件で、建設工事が軒並み95〜100点になった。原因は公告文に含まれる
    「工事写真撮影」「塗装の密着性」「密着造林型」などの専門用語と、
    「中小企業者の受注機会確保」「環境への配慮」といった定型文だった。
    """
    from src.scoring.scorer import score_fields

    # 実データから採取した公告文の定型文(どの工事案件にも含まれる)
    boilerplate = (
        "本工事は中小企業者の受注機会の確保に努めるものとする。"
        "環境への配慮を行い、廃棄物のリサイクルに努めること。"
        "災害防止および福祉の増進に留意すること。"
        "工事写真撮影を行い、着手前後の映像を記録し書類を編集して提出すること。"
        "塗装は下地との密着を確認すること。"
        "教育委員会および地域住民、学生への周知を行う。建設業許可を要する。"
    )

    for title in [
        "総【JV】7-108-202防災備蓄倉庫新築工事",
        "【入札公告】津屋崎中学校校舎増築1期工事",
        "狭山市立柏原中学校除湿温度保持工事",
        "南大樋町地区 口径100から50mm配水管更新工事",
        "愛称ロード標識撤去業務委託",
    ]:
        result = score_fields(title, description=boilerplate)
        assert result.has_anchor is False, f"工事案件が映像案件と判定された: {title}"
        assert result.keyword_score == 0, f"{title} が{result.keyword_score}点になった"
        assert result.matches["documentary_match"] is False
        assert result.matches["video_match"] is False

    # 林業の「密着造林型」を密着取材と誤認しないこと
    forestry = score_fields("鍋山国有林森林整備事業(誘導伐:密着造林型)", description=boilerplate)
    assert forestry.has_anchor is False
    assert forestry.keyword_score == 0


def test_shared_listing_page_does_not_leak_between_cases():
    """公告文が一覧ページ全体である場合に、他案件の文章で誤検出しないこと。

    実データで宮崎県の無線LAN構築・防災ネットワーク保守・パスポート輸送が
    揃って65点になった。同じ公告ページを共有しており、そのページに
    映像案件が含まれていたため全件が映像案件と誤認されていた。
    """
    from src.scoring.scorer import score_fields

    # 一覧ページには本物の映像案件の文章が混ざっている
    listing_page = (
        "令和8年度 県政情報発信のための動画制作業務委託について入札を実施します。"
        "ドキュメンタリー形式での記録映像の制作を含みます。"
        "その他の公告: 無線LAN環境構築業務委託、旅券等輸送業務委託、総合防災情報ネットワーク点検保守委託。"
    )

    for title in [
        "令和8年度無線LAN環境構築業務委託に係る入札公告",
        "旅券(パスポート)等輸送業務委託に係る一般競争入札の実施について",
        "総合防災情報ネットワーク関連の点検保守委託に係る一般競争入札について",
        "【電子入札】【電子契約】認知度調査・広報媒体効果測定",
    ]:
        result = score_fields(title, description=listing_page)
        assert result.has_anchor is False, f"一覧ページの他案件で誤検出された: {title}"
        assert result.keyword_score == 0, f"{title} が{result.keyword_score}点になった"

    # 同じページを公告文に持っていても、案件名が映像案件なら正しく拾う
    genuine = score_fields("令和8年度 県政情報発信のための動画制作業務委託", description=listing_page)
    assert genuine.has_anchor is True
    assert genuine.anchor_source == "title"


def test_url_encoded_project_name_is_decoded():
    """案件名がURLエンコードされたまま入っている場合にデコードすること。"""
    from src.collectors.kkj import decode_project_name

    decoded = decode_project_name("%E5%8B%95%E7%94%BB%E5%88%B6%E4%BD%9C%E6%A5%AD%E5%8B%99")
    assert decoded == "動画制作業務"

    # 通常の案件名はそのまま
    assert decode_project_name("地域プロモーション動画制作業務") == "地域プロモーション動画制作業務"
    assert decode_project_name(None) is None

    # デコード後にキーワード判定が効くこと
    from src.scoring.scorer import score_fields

    assert score_fields(decoded).has_anchor is True


def test_real_video_projects_still_score():
    """誤判定を潰しても、本物の映像案件は拾えること。"""
    from src.scoring.scorer import score_fields

    documentary = score_fields(
        "伝統工芸職人の技を伝えるドキュメンタリー動画制作業務",
        "後継者不足に悩む職人に密着取材し、その物語を記録する。",
    )
    assert documentary.has_anchor is True
    assert documentary.matches["documentary_match"] is True
    assert documentary.keyword_score >= 60

    # 案件名に映像系の語があれば裏付けになる
    title_anchor = score_fields("地域プロモーション動画制作業務委託", "観光産業の活性化を目的とする。")
    assert title_anchor.has_anchor is True
    assert title_anchor.matches["video_match"] is True

    # 仕様書にドキュメンタリー記述があれば、案件名に無くても裏付けになる
    from_spec = score_fields(
        "地域資源活用事業に係る記録業務",
        "事業者への密着取材を行いドキュメンタリー形式で記録すること。",
    )
    assert from_spec.has_anchor is True
    assert from_spec.matches["documentary_match"] is True


def test_theme_only_projects_are_capped_not_discarded():
    """裏付けが無くても、案件名にテーマがあれば上限付きで拾う(要件39)。

    ただし公告文の定型文だけに反応してはいけない。
    """
    from src.scoring.keywords import load_keywords
    from src.scoring.scorer import score_fields

    cap = load_keywords()["no_anchor_max_score"]

    # 案件名にテーマがある → 上限付きで候補に残す
    theme_in_title = score_fields("若者の地域定着促進に関する関係人口創出事業", "")
    assert theme_in_title.has_anchor is False
    assert 0 < theme_in_title.keyword_score <= cap

    # 定型文にしかテーマが無い → 0点
    boilerplate_only = score_fields(
        "配水管更新工事", "中小企業者への配慮と環境保全、地域活性化に資する工事とする。"
    )
    assert boilerplate_only.keyword_score == 0


def test_deprioritized_work_is_penalized():
    """式典記録・議会中継・防犯カメラ等は優先度を下げる(要件39)。"""
    from src.scoring.scorer import score_fields

    ceremony = score_fields("開庁式典記録映像制作業務", "式典撮影を行う。")
    assert ceremony.deprioritized is True

    plain_pr = score_fields("観光振興PR動画制作業務", "観光地の魅力を発信する。")
    assert ceremony.keyword_score < plain_pr.keyword_score, "式典記録は通常のPR動画より低いこと"


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
