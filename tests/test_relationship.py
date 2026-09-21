"""SISIDEN Relationship OS の自動テスト。

重複判定→CSVインポート→Interaction記録→Project人物レコメンド→
オプトアウト除外→MCPツール(campaignフロー)→重複統合、までを一通り検証する。

実行方法: python3 tests/test_relationship.py
または:  python3 -m pytest tests/test_relationship.py -v
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.relationship.database import db
from src.relationship.importers.eight_csv import import_eight_csv
from src.relationship.importers.generic_csv import import_generic_csv
from src.relationship.matching.scorer import recommend_people_for_project
from src.relationship.mcp import tools as mcp_tools

FIXTURES = ROOT / "tests" / "relationship_fixtures"
SCHEMA_PATH = ROOT / "src" / "relationship" / "database" / "schema.sql"


def _make_temp_db() -> Path:
    tmp_dir = Path(tempfile.mkdtemp())
    db_path = tmp_dir / "test_relationship.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return db_path


# ============================================================
# 重複判定
# ============================================================

def test_email_match_updates_existing_person_without_duplicate():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        r1 = db.upsert_person(conn, {"name": "山田太郎", "email": "Yamada@Example.com", "source": "manual"})
        assert r1["action"] == "created"

        # 大文字小文字・前後空白が違っても同一メールとして扱う
        r2 = db.upsert_person(conn, {"name": "山田太郎", "email": " yamada@example.com ", "phone": "090-1111-2222", "source": "csv_sales"})
        assert r2["action"] == "matched_email"
        assert r2["person_id"] == r1["person_id"]

        count = conn.execute("SELECT COUNT(*) c FROM persons").fetchone()["c"]
        assert count == 1, "メール一致は新規行を作らない"

        person = db.get_person_detail(conn, r1["person_id"])
        assert person["phone"] == "09011112222", "空欄だったphoneが補完されること"
    finally:
        conn.close()


def test_phone_match_creates_duplicate_candidate_not_auto_merge():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        r1 = db.upsert_person(conn, {"name": "鈴木一郎", "phone": "03-1234-5678", "source": "eight"})
        r2 = db.upsert_person(conn, {"name": "鈴木一郎", "phone": "0312345678", "source": "csv_sales"})

        assert r2["action"] == "created_with_duplicate_candidates"
        assert r1["person_id"] != r2["person_id"], "確信度が低い一致は自動統合せず別レコードのまま"

        count = conn.execute("SELECT COUNT(*) c FROM persons").fetchone()["c"]
        assert count == 2

        candidates = db.list_duplicate_candidates(conn, status="pending")
        assert len(candidates) == 1
        assert candidates[0]["match_basis"] == "phone"
        assert candidates[0]["confidence"] == "medium"
    finally:
        conn.close()


def test_resolve_duplicate_merge():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        r1 = db.upsert_person(conn, {"name": "高橋花子", "phone": "090-0000-1111", "notes": "初回メモ", "source": "eight"})
        r2 = db.upsert_person(conn, {"name": "高橋花子", "phone": "09000001111", "email": "takahashi@example.com", "source": "csv_sales"})
        dup = db.list_duplicate_candidates(conn, status="pending")[0]

        result = db.resolve_duplicate(conn, dup["id"], action="merge", keep_person_id=r1["person_id"], resolved_by="tester")
        assert result["action"] == "merged"

        merged_row = conn.execute("SELECT is_deleted, merged_into_id FROM persons WHERE id = ?", (r2["person_id"],)).fetchone()
        assert merged_row["is_deleted"] == 1
        assert merged_row["merged_into_id"] == r1["person_id"]

        kept = db.get_person_detail(conn, r1["person_id"])
        assert kept["email"] == "takahashi@example.com", "統合時に空欄が補完されること"
        assert kept["notes"] == "初回メモ", "既存の値は上書きされないこと"
    finally:
        conn.close()


# ============================================================
# CSVインポート
# ============================================================

def test_import_eight_csv():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        result = import_eight_csv(conn, FIXTURES / "eight_sample.csv")
        assert result["total_rows"] == 4
        assert result["new_persons"] == 4
        assert not result["errors"]

        tanaka = conn.execute("SELECT * FROM persons WHERE name = ?", ("田中太郎",)).fetchone()
        assert tanaka is not None
        assert tanaka["source"] == "eight"
        assert tanaka["first_met_at"] == "2025-05-10"

        tags = db.get_person_tags(conn, tanaka["id"])
        assert "自治体" in tags and "地方創生" in tags

        org = conn.execute("SELECT * FROM organizations WHERE id = ?", (tanaka["organization_id"],)).fetchone()
        assert org["name"] == "港区役所"

        interactions = conn.execute("SELECT * FROM interactions WHERE person_id = ?", (tanaka["id"],)).fetchall()
        assert len(interactions) == 1
        assert interactions[0]["channel"] == "business_card"

        # 同じ会社の2人が同じorganizationに紐づく(組織の重複作成を防ぐ)
        suzuki = conn.execute("SELECT * FROM persons WHERE name = ?", ("鈴木花子",)).fetchone()
        takahashi = conn.execute("SELECT * FROM persons WHERE name = ?", ("高橋実",)).fetchone()
        assert suzuki["organization_id"] == takahashi["organization_id"]
    finally:
        conn.close()


def test_import_generic_csv_media_and_sales():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        media_result = import_generic_csv(
            conn, FIXTURES / "media_list_sample.csv", source="csv_media", default_tags=["記者"], is_media=True
        )
        assert media_result["new_persons"] == 2

        nakamura = conn.execute("SELECT * FROM persons WHERE name = ?", ("中村建太",)).fetchone()
        media_profile = conn.execute("SELECT * FROM media_profiles WHERE person_id = ?", (nakamura["id"],)).fetchone()
        assert media_profile is not None
        assert media_profile["genre"] == "建設・都市開発"
        tags = db.get_person_tags(conn, nakamura["id"])
        assert "記者" in tags and "メディア" in tags

        sales_result = import_generic_csv(
            conn, FIXTURES / "sales_list_municipality.csv", source="csv_sales", default_org_type="municipality"
        )
        assert sales_result["new_persons"] == 2
        sato = conn.execute("SELECT * FROM persons WHERE name = ?", ("佐藤一郎",)).fetchone()
        org = conn.execute("SELECT * FROM organizations WHERE id = ?", (sato["organization_id"],)).fetchone()
        assert org["type"] == "municipality"
    finally:
        conn.close()


# ============================================================
# Interaction・関係性強度
# ============================================================

def test_log_interaction_updates_last_contact_and_strength():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        person_id = db.upsert_person(conn, {"name": "テスト太郎", "email": "test@example.com"})["person_id"]
        before = db.get_person_detail(conn, person_id)
        assert before["relationship_strength"] == 0

        db.log_interaction(
            conn,
            {
                "person_id": person_id,
                "date": "2026-01-15",
                "channel": "meeting",
                "direction": "outbound",
                "subject": "打ち合わせ",
                "reaction": "前向きな反応",
            },
        )
        after = db.get_person_detail(conn, person_id)
        assert after["last_contact_at"] == "2026-01-15"
        assert after["relationship_strength"] == 5  # reactionありは+5
        assert len(after["recent_interactions"]) == 1

        try:
            db.log_interaction(conn, {"person_id": person_id, "date": "2026-01-16", "channel": "invalid_channel"})
            raise AssertionError("不正なchannelはValueErrorになるべき")
        except ValueError:
            pass
    finally:
        conn.close()


# ============================================================
# Project → 人物レコメンド(MEDIA/SALES/RELATIONSHIP/AMPLIFICATION)
# ============================================================

def _seed_recommend_scenario(conn: sqlite3.Connection) -> dict:
    import_eight_csv(conn, FIXTURES / "eight_sample.csv")
    import_generic_csv(conn, FIXTURES / "media_list_sample.csv", source="csv_media", default_tags=["記者"], is_media=True)
    import_generic_csv(conn, FIXTURES / "sales_list_municipality.csv", source="csv_sales", default_org_type="municipality")

    influencer_id = db.upsert_person(
        conn,
        {"name": "地域インフルエンサー", "email": "influencer@example.com", "location": "東京都", "notes": "まちづくり発信で人気"},
    )["person_id"]
    db.add_person_tags(conn, influencer_id, ["インフルエンサー"], category="role")

    blocked_id = db.upsert_person(
        conn, {"name": "配信拒否記者", "email": "blocked@example.com", "location": "東京都"}
    )["person_id"]
    db.upsert_media_profile(conn, blocked_id, {"genre": "建設・都市開発", "area": "関東"})
    db.set_optout(conn, blocked_id, "media_pitch", "do_not_contact")

    project_id = db.create_project(
        conn,
        {
            "project_name": "鹿島TREE 第3話",
            "client": "鹿島建設",
            "main_theme": "建設・まちづくり",
            "social_issue": "地方創生",
            "industry": "建設",
            "location": "東京都",
            "keywords": ["建設", "まちづくり", "地方創生"],
        },
    )
    return {"project_id": project_id, "influencer_id": influencer_id, "blocked_id": blocked_id}


def test_recommend_people_for_project_classification_and_reasons():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        seed = _seed_recommend_scenario(conn)
        project = db.get_project(conn, seed["project_id"])
        buckets = recommend_people_for_project(conn, project, min_score=15)

        media_names = {c["name"] for c in buckets["MEDIA"]}
        assert "中村建太" in media_names, "建設・都市開発担当の記者はMEDIA候補に入るべき"
        for c in buckets["MEDIA"]:
            assert c["reason"], "MEDIA候補には必ず理由が付く"
            assert 0 <= c["score"] <= 100

        assert "配信拒否記者" not in media_names, "media_pitch_status=do_not_contactは除外されるべき"

        sales_names = {c["name"] for c in buckets["SALES"]}
        assert "佐藤一郎" in sales_names, "自治体の地方創生担当はSALES候補に入るべき"

        amp_names = {c["name"] for c in buckets["AMPLIFICATION"]}
        assert "地域インフルエンサー" in amp_names

        # RELATIONSHIPは既存接点はあるがMEDIA/SALES/AMPLIFICATIONに分類されない人物の受け皿
        assert isinstance(buckets["RELATIONSHIP"], list)
    finally:
        conn.close()


def test_recommend_respects_min_score_and_limit():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        seed = _seed_recommend_scenario(conn)
        project = db.get_project(conn, seed["project_id"])
        buckets = recommend_people_for_project(conn, project, limit_per_category=1, min_score=15)
        for category, items in buckets.items():
            assert len(items) <= 1
            for item in items:
                assert item["score"] >= 15
    finally:
        conn.close()


# ============================================================
# MCPツール層(campaignフロー: 候補抽出→承認→送信→Interaction自動生成)
# ============================================================

def test_mcp_tools_campaign_flow_end_to_end():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        seed = _seed_recommend_scenario(conn)
    finally:
        conn.close()

    project_result = mcp_tools.get_project(seed["project_id"], db_path=str(db_path))
    assert project_result["found"] is True

    reco = mcp_tools.recommend_people_for_project(seed["project_id"], db_path=str(db_path))
    assert reco["found"] is True
    media_candidates = reco["candidates"]["MEDIA"]
    assert media_candidates, "MEDIA候補が1件以上あるはず"

    campaign = mcp_tools.create_campaign(
        {"name": "鹿島TREE 第3話 公開キャンペーン", "project_id": seed["project_id"], "campaign_type": "mixed"},
        db_path=str(db_path),
    )
    campaign_id = campaign["campaign_id"]

    audience = mcp_tools.add_campaign_audience(campaign_id, "記者向け", db_path=str(db_path))

    target = media_candidates[0]
    added = mcp_tools.add_campaign_targets(
        campaign_id,
        [
            {
                "person_id": target["person_id"],
                "category": "MEDIA",
                "score": target["score"],
                "reason": target["reason"],
                "draft_text": "Claudeが生成した記者向けPitch文(ダミー)",
            }
        ],
        audience_id=audience["audience_id"],
        db_path=str(db_path),
    )
    assert added["count"] == 1
    campaign_target_id = added["campaign_target_ids"][0]

    approved = mcp_tools.update_campaign_target_status(
        campaign_target_id, "approved", approved_by="yoshiko", db_path=str(db_path)
    )
    assert approved["found"] is True
    assert approved["campaign_target"]["status"] == "approved"

    sent = mcp_tools.update_campaign_target_status(
        campaign_target_id, "sent", approved_by="yoshiko", db_path=str(db_path)
    )
    assert sent["campaign_target"]["status"] == "sent"
    assert sent["campaign_target"]["sent_at"] is not None

    person_detail = mcp_tools.get_person(target["person_id"], db_path=str(db_path))
    interactions = person_detail["person"]["recent_interactions"]
    assert any(i["channel"] == "media_pitch" for i in interactions), "sentになったらInteractionが自動記録される"


def test_mcp_search_people_natural_language_style_filters():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        _seed_recommend_scenario(conn)
    finally:
        conn.close()

    # 「教育関係者だけ抽出して」相当
    edu = mcp_tools.search_people(tags=["教育"], db_path=str(db_path))
    assert edu["count"] >= 1
    assert all("教育" in r["tags"] for r in edu["results"])

    # 「過去に返信があった記者だけ出して」相当(このシナリオでは記者に返信履歴なし=0件を確認)
    replied_media = mcp_tools.search_people(is_media=True, has_reply=True, db_path=str(db_path))
    assert replied_media["count"] == 0

    # 「自治体職員の中で...」相当
    municipal = mcp_tools.search_people(organization_type="municipality", db_path=str(db_path))
    assert municipal["count"] >= 1
    assert all(r["organization_type"] == "municipality" for r in municipal["results"])


def test_mcp_dashboard_and_duplicate_review():
    db_path = _make_temp_db()
    conn = db.get_connection(db_path)
    try:
        db.upsert_person(conn, {"name": "A", "phone": "0311112222"})
        db.upsert_person(conn, {"name": "A", "phone": "03-1111-2222"})
    finally:
        conn.close()

    dashboard = mcp_tools.get_dashboard(db_path=str(db_path))
    assert dashboard["pending_duplicate_candidates"] == 1

    dups = mcp_tools.list_duplicate_candidates(db_path=str(db_path))
    assert dups["count"] == 1
    resolved = mcp_tools.resolve_duplicate(dups["results"][0]["id"], "reject", db_path=str(db_path))
    assert resolved["action"] == "rejected"


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")


if __name__ == "__main__":
    _run_all()
