"""SISIDEN MEDIA の正本データ管理とSTUDIO連携レイヤーのテスト。

実行方法: python3 -m pytest tests/test_media.py -v
または:  python3 tests/test_media.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.request
import xml.dom.minidom
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml

from src.media import jsonld
from src.media.api import payload
from src.media.api.server import create_server
from src.media.content import ERROR, load_repository, validate
from src.media.exporters import csv_export, wxr
from src.media.schema import load_schema


def _sample_repo():
    return load_repository()


def test_schema_loads_and_references_resolve():
    schema = load_schema(force_reload=True)
    assert "documentaries" in schema.models
    assert len(schema.models) == 8

    articles = schema.model("articles")
    assert articles.path == "stories"
    assert articles.get_property("documentary").ref_target == "documentaries"
    assert articles.get_property("documentary").is_single_ref
    assert articles.get_property("people").is_multi_ref

    # 参照先が未定義のモデルを指していないこと（load_schema内で検証済み）
    for model in schema.models.values():
        for prop in model.ref_properties:
            assert prop.ref_target in schema.models


def test_url_design_matches_spec():
    schema = load_schema()
    assert schema.url_for("documentaries", "tonkan") == \
        "https://sisicreation.com/sisiden/documentary/tonkan"
    assert schema.url_for("articles", "tonkan-interview-ogura") == \
        "https://sisicreation.com/sisiden/stories/tonkan-interview-ogura"
    assert schema.url_for("issues", "youth-community-space") == \
        "https://sisicreation.com/sisiden/issues/youth-community-space"


def test_sample_content_has_no_errors():
    repo = _sample_repo()
    errors = [i for i in validate(repo) if i.level == ERROR]
    assert errors == [], "\n".join(str(e) for e in errors)


def test_validation_detects_broken_reference_and_missing_required():
    with tempfile.TemporaryDirectory() as tmp:
        content_dir = Path(tmp)
        (content_dir / "articles").mkdir(parents=True)
        (content_dir / "articles" / "broken.yaml").write_text(
            yaml.safe_dump({
                "title": "テスト",
                "documentary": "does-not-exist",
                "status": "公開",
            }, allow_unicode=True),
            encoding="utf-8",
        )
        repo = load_repository(content_dir=content_dir)
        messages = [str(i) for i in validate(repo) if i.level == ERROR]

        assert any("参照先が存在しません" in m for m in messages)
        assert any("必須プロパティが未入力です: lead" in m for m in messages)


def test_validation_blocks_publishing_people_without_consent():
    with tempfile.TemporaryDirectory() as tmp:
        content_dir = Path(tmp)
        (content_dir / "people").mkdir(parents=True)
        (content_dir / "people" / "someone.yaml").write_text(
            yaml.safe_dump({
                "name": "テスト太郎",
                "name_kana": "てすとたろう",
                "role": "主人公",
                "title": "テスト",
                "portrait": "https://example.com/p.jpg",
                "lead": "テスト",
                "profile": "テスト",
                "consent_status": "確認中",
                "status": "公開",
            }, allow_unicode=True),
            encoding="utf-8",
        )
        repo = load_repository(content_dir=content_dir)
        messages = [str(i) for i in validate(repo) if i.level == ERROR]
        assert any("取得済" in m for m in messages)


def test_jsonld_expands_multi_references():
    """STUDIOの構造化データ欄では難しいマルチ参照の配列展開を、ここで解決する。"""
    repo = _sample_repo()
    doc = repo.get("documentaries", "tonkan")
    built = jsonld.documentary(repo, doc)

    video = built["@graph"][0]
    assert video["@type"] == "VideoObject"
    assert video["@id"] == "https://sisicreation.com/sisiden/documentary/tonkan#video"
    assert video["about"] == [
        {"@id": "https://sisicreation.com/sisiden/issues/youth-community-space#issue"}
    ]
    assert video["actor"] == [
        {"@id": "https://sisicreation.com/sisiden/people/rion-ogura#person"}
    ]

    breadcrumb = built["@graph"][1]
    assert breadcrumb["@type"] == "BreadcrumbList"
    assert len(breadcrumb["itemListElement"]) == 3


def test_article_jsonld_links_to_documentary_and_author():
    repo = _sample_repo()
    article = repo.get("articles", "tonkan-interview-ogura")
    node = jsonld.article(repo, article)["@graph"][0]

    assert node["@type"] == "Article"
    assert node["isPartOf"]["@id"].endswith("/documentary/tonkan#video")
    assert node["author"]["@id"].endswith("/people/sisiden-editorial#person")
    assert node["articleSection"] == "証言"
    assert node["datePublished"] == "2026-09-20"


def test_organization_jsonld_declares_alternate_names():
    repo = _sample_repo()
    org = jsonld.organization(repo)
    # 表記揺れ（SisiDen）を同一実体としてAIに伝える
    assert "SisiDen" in org["alternateName"]
    assert org["parentOrganization"]["name"] == "株式会社シシクリエイション"


def test_api_payload_embeds_relations_and_jsonld():
    repo = _sample_repo()
    detail = payload.detail_payload(repo, "documentaries", "tonkan")

    assert detail["slug"] == "tonkan"
    assert detail["url"].endswith("/documentary/tonkan")
    assert detail["areas"][0]["name"] == "横浜"
    assert detail["primary_issue"]["slug"] == "youth-community-space"
    assert json.loads(detail["jsonld"])["@graph"][0]["@type"] == "VideoObject"


def test_api_list_payload_excludes_drafts_and_paginates():
    repo = _sample_repo()

    published = payload.list_payload(repo, "categories", limit=3)
    assert published["totalCount"] == 5
    assert published["limit"] == 3
    assert len(published["contents"]) == 3
    assert published["contents"][0]["slug"] == "interview"

    # サンプルの作品は下書きなので公開一覧には出ない
    drafts = payload.list_payload(repo, "documentaries")
    assert drafts["totalCount"] == 0
    assert payload.list_payload(repo, "documentaries", include_drafts=True)["totalCount"] == 1


def test_api_list_payload_filters():
    repo = _sample_repo()
    result = payload.list_payload(
        repo, "articles", filters={"documentary": "tonkan"}, include_drafts=True
    )
    assert result["totalCount"] == 1
    assert result["contents"][0]["slug"] == "tonkan-interview-ogura"

    empty = payload.list_payload(
        repo, "articles", filters={"documentary": "unknown"}, include_drafts=True
    )
    assert empty["totalCount"] == 0


def test_api_server_serves_data_connect_endpoints():
    httpd = create_server(host="127.0.0.1", port=0, repository=_sample_repo())
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}/api/v1"

        with urllib.request.urlopen(f"{base}/health", timeout=5) as res:
            health = json.load(res)
        assert health["status"] == "ok"
        assert health["models"]["categories"] == 5

        with urllib.request.urlopen(f"{base}/categories?limit=2", timeout=5) as res:
            listing = json.load(res)
        assert listing["totalCount"] == 5
        assert len(listing["contents"]) == 2

        with urllib.request.urlopen(f"{base}/areas/yokohama", timeout=5) as res:
            detail = json.load(res)
        assert detail["name"] == "横浜"

        try:
            urllib.request.urlopen(f"{base}/areas/nowhere", timeout=5)
            raise AssertionError("404が返るべき")
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_wxr_export_is_well_formed_and_keeps_interview_facts():
    repo = _sample_repo()
    with tempfile.TemporaryDirectory() as tmp:
        path = wxr.export_articles(repo, Path(tmp))
        xml.dom.minidom.parse(str(path))  # 構文エラーがあれば例外
        text = path.read_text(encoding="utf-8")

    assert "<wp:post_name>tonkan-interview-ogura</wp:post_name>" in text
    assert "sisiden_documentary" in text
    # リレーションはWXRの語彙にないため、本文末尾に取材情報を残している
    assert "この記事について" in text
    assert "2026-08-12" in text


def test_wxr_escapes_cdata_terminator():
    assert "]]]]><![CDATA[>" in wxr._cdata("危険な文字列 ]]> を含む本文")


def test_markdown_to_html_handles_headings_and_quotes():
    html = wxr.markdown_to_html("## 見出し\n\n本文です。\n\n> 引用です。")
    assert "<h3>見出し</h3>" in html
    assert "<p>本文です。</p>" in html
    assert "<blockquote><p>引用です。</p></blockquote>" in html


def test_csv_export_and_setup_sheet():
    repo = _sample_repo()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        paths = csv_export.export_all(repo, out)
        assert len(paths) == 8

        articles_csv = (out / "articles.csv").read_text(encoding="utf-8-sig")
        assert "tonkan-interview-ogura" in articles_csv
        assert "youth|ibasho" in articles_csv  # マルチ参照はパイプ区切り

        sheet = csv_export.export_studio_setup_sheet(repo, out).read_text(encoding="utf-8-sig")
        assert "DOCUMENTARIES,people,登場人物,参照,PEOPLE,マルチセレクト" in sheet
        assert "ARTICLES,documentary,関連ドキュメンタリー,参照,DOCUMENTARIES,シングルセレクト" in sheet


def test_minimal_setup_sheet_covers_only_phase1_required_properties():
    """初日に作る分だけに絞ったシート。プロパティは後から追加できるため。"""
    repo = _sample_repo()
    with tempfile.TemporaryDirectory() as tmp:
        path = csv_export.export_studio_setup_sheet(
            repo, Path(tmp), models=csv_export.PHASE1_MODELS, required_only=True,
        )
        rows = path.read_text(encoding="utf-8-sig").splitlines()[1:]

    assert path.name == "studio_cms_setup_minimal.csv"
    assert all(row.split(",")[6] == "●" for row in rows)

    models = {row.split(",")[0] for row in rows}
    assert models == {"CATEGORIES", "PEOPLE", "DOCUMENTARIES", "ARTICLES"}

    # Phase 1に含まれないモデルへの参照は落とす（AREASはまだ作らないため）
    assert not any(row.split(",")[4] == "AREAS" for row in rows)
    assert any("DOCUMENTARIES,people,登場人物,参照,PEOPLE" in row for row in rows)


def test_redirect_map_drops_only_the_first_path_segment():
    """独立ドメイン移行を「第1階層を落とすだけ」で済ませる設計の検証。"""
    repo = _sample_repo()
    with tempfile.TemporaryDirectory() as tmp:
        path = csv_export.export_redirect_map(repo, Path(tmp), "https://sisiden.jp")
        rows = path.read_text(encoding="utf-8-sig").splitlines()

    assert ("https://sisicreation.com/sisiden/documentary/tonkan,"
            "https://sisiden.jp/documentary/tonkan,301") in rows


def test_date_fields_are_parsed_as_dates():
    repo = _sample_repo()
    article = repo.get("articles", "tonkan-interview-ogura")
    assert isinstance(article["interview_date"], date)
    assert article["interview_date"].isoformat() == "2026-08-12"


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
    print(f"\n{len(tests)}件のテストがすべて通りました。")


if __name__ == "__main__":
    _run_all()
