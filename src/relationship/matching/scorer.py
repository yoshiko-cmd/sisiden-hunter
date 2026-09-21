"""Project → 人物 のルールベース・マッチングエンジン(AI/LLM API不使用)。

「テーマ一致30 / 業界一致20 / 過去の関係性20 / 最近の接触10 / 地域一致10 / 過去反応10」
の100点満点で人物ごとにスコアを計算し、MEDIA/SALES/RELATIONSHIP/AMPLIFICATIONへ分類する。
スコアはランキングのための内部指標であり、Claudeへは必ず理由文とセットで返す
(数字だけでなく「なぜこの人が候補なのか」を人間が読める形にする)。

オプトアウト(do_not_contact/unsubscribed)は、ここで必ず除外する。
文面生成そのものはこのモジュールでは行わない(Claude側の役割、要件15)。
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from typing import Any

_MEDIA_TAGS = {"記者", "編集者", "メディア"}
_AMPLIFICATION_TAGS = {"インフルエンサー", "パートナー"}
_SALES_ORG_TYPES = {"company", "municipality", "school", "university", "ngo", "association"}

_TERM_SPLIT_RE = re.compile(r"[、,\s・/]+")


def _split_terms(*texts: str | None) -> list[str]:
    terms: list[str] = []
    for text in texts:
        if not text:
            continue
        for part in _TERM_SPLIT_RE.split(text):
            part = part.strip()
            if len(part) >= 2 and part not in terms:
                terms.append(part)
    return terms


def _days_since(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        d = datetime.fromisoformat(date_str[:10]).date()
    except ValueError:
        return None
    return (date.today() - d).days


def _recency_score(days: int | None) -> int:
    if days is None:
        return 0
    if days <= 30:
        return 10
    if days <= 90:
        return 7
    if days <= 180:
        return 5
    if days <= 365:
        return 2
    return 0


def _blocked(person: dict[str, Any], category: str) -> bool:
    statuses = (person.get("newsletter_status"), person.get("sales_email_status"), person.get("media_pitch_status"))
    if "do_not_contact" in statuses:
        return True
    if category == "MEDIA":
        return person.get("media_pitch_status") == "unsubscribed"
    if category == "SALES":
        return person.get("sales_email_status") == "unsubscribed"
    return person.get("newsletter_status") == "unsubscribed"  # RELATIONSHIP / AMPLIFICATION


def classify_person(tags: set[str], has_media_profile: bool, organization_type: str | None) -> str:
    if has_media_profile or (tags & _MEDIA_TAGS):
        return "MEDIA"
    if tags & _AMPLIFICATION_TAGS:
        return "AMPLIFICATION"
    if organization_type in _SALES_ORG_TYPES:
        return "SALES"
    return "RELATIONSHIP"


def _fetch_persons_with_context(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT p.*, o.name AS organization_name, o.type AS organization_type,
               o.industry AS organization_industry, o.location AS organization_location
        FROM persons p
        LEFT JOIN organizations o ON o.id = p.organization_id
        WHERE p.is_deleted = 0
        """
    ).fetchall()
    persons = [dict(r) for r in rows]

    tag_rows = conn.execute(
        "SELECT pt.person_id, t.name FROM person_tags pt JOIN tags t ON t.id = pt.tag_id"
    ).fetchall()
    tags_by_person: dict[int, set[str]] = {}
    for r in tag_rows:
        tags_by_person.setdefault(r["person_id"], set()).add(r["name"])

    media_rows = conn.execute("SELECT * FROM media_profiles").fetchall()
    media_by_person = {r["person_id"]: dict(r) for r in media_rows}

    reaction_rows = conn.execute(
        "SELECT DISTINCT person_id FROM interactions WHERE reaction IS NOT NULL AND reaction != ''"
    ).fetchall()
    has_reaction = {r["person_id"] for r in reaction_rows}

    coverage_rows = conn.execute("SELECT DISTINCT person_id FROM coverage WHERE person_id IS NOT NULL").fetchall()
    has_coverage = {r["person_id"] for r in coverage_rows}

    for p in persons:
        p["_tags"] = tags_by_person.get(p["id"], set())
        p["_media_profile"] = media_by_person.get(p["id"])
        p["_has_positive_reaction"] = p["id"] in has_reaction or p["id"] in has_coverage

    return persons


def score_person_for_project(project: dict[str, Any], person: dict[str, Any]) -> dict[str, Any]:
    """1人物のスコアと理由を計算する。"""
    query_terms = _split_terms(
        project.get("main_theme"),
        project.get("social_issue"),
        project.get("industry"),
        *(project.get("keywords") or []),
    )

    media = person.get("_media_profile") or {}
    person_texts = [
        *person.get("_tags", []),
        person.get("organization_industry"),
        person.get("organization_name"),
        person.get("notes"),
        media.get("genre"),
        media.get("area"),
        media.get("interest_themes"),
        media.get("outlet_name"),
    ]
    person_text_blob = " ".join(t for t in person_texts if t)

    matched_terms = [term for term in query_terms if term in person_text_blob]
    theme_score = min(30, 10 * len(matched_terms))

    industry_score = 0
    if project.get("industry") and person.get("organization_industry"):
        proj_industry = project["industry"].strip()
        org_industry = person["organization_industry"].strip()
        if proj_industry and org_industry:
            if proj_industry.lower() == org_industry.lower():
                industry_score = 20
            elif proj_industry in org_industry or org_industry in proj_industry:
                industry_score = 10

    relationship_score = round((person.get("relationship_strength") or 0) / 100 * 20)

    days = _days_since(person.get("last_contact_at"))
    recency_score = _recency_score(days)

    location_score = 0
    proj_location = (project.get("location") or "").strip()
    person_location = " ".join(filter(None, [person.get("location"), person.get("organization_location")]))
    if proj_location and person_location and proj_location in person_location:
        location_score = 10

    past_reaction_score = 10 if person.get("_has_positive_reaction") else 0

    total = theme_score + industry_score + relationship_score + recency_score + location_score + past_reaction_score
    total = min(100, total)

    reasons: list[str] = []
    if matched_terms:
        reasons.append(f"テーマ「{'・'.join(matched_terms[:3])}」に関心・実績が一致。")
    if industry_score:
        reasons.append(f"{person.get('organization_industry')}分野で案件と業界が一致。")
    if media.get("genre") and any(t in (project.get("main_theme") or "") + (project.get("social_issue") or "") for t in _split_terms(media.get("genre"))):
        reasons.append(f"担当ジャンル「{media.get('genre')}」がテーマと近い。")
    if relationship_score >= 10:
        reasons.append(f"関係性強度{person.get('relationship_strength')}点の既存関係者。")
    if recency_score >= 7 and days is not None:
        reasons.append(f"直近{days}日以内に接点あり。")
    elif recency_score == 0 and days is not None and days > 365:
        pass  # 理由には含めない(ネガティブ材料)
    if location_score:
        reasons.append(f"活動エリアが案件の所在地(「{proj_location}」)と一致。")
    if past_reaction_score:
        reasons.append("過去に返信・掲載などの好意的な反応実績あり。")
    if not reasons:
        reasons.append("案件テーマとの直接一致は弱いが、既存の接点があるため候補に含めた。")

    return {
        "score": total,
        "reason": " ".join(reasons[:3]),
        "score_breakdown": {
            "theme": theme_score,
            "industry": industry_score,
            "relationship": relationship_score,
            "recency": recency_score,
            "location": location_score,
            "past_reaction": past_reaction_score,
        },
    }


def recommend_people_for_project(
    conn: sqlite3.Connection,
    project: dict[str, Any],
    *,
    categories: list[str] | None = None,
    limit_per_category: int = 10,
    min_score: int = 15,
) -> dict[str, list[dict[str, Any]]]:
    """Projectに対する人物候補をMEDIA/SALES/RELATIONSHIP/AMPLIFICATIONに分類して返す。"""
    all_categories = ["MEDIA", "SALES", "RELATIONSHIP", "AMPLIFICATION"]
    wanted = set(categories) if categories else set(all_categories)

    persons = _fetch_persons_with_context(conn)
    buckets: dict[str, list[dict[str, Any]]] = {c: [] for c in all_categories}

    for person in persons:
        category = classify_person(person["_tags"], person["_media_profile"] is not None, person.get("organization_type"))
        if category not in wanted:
            continue
        if _blocked(person, category):
            continue

        scored = score_person_for_project(project, person)
        if scored["score"] < min_score:
            continue

        buckets[category].append(
            {
                "person_id": person["id"],
                "name": person["name"],
                "organization_name": person.get("organization_name"),
                "job_title": person.get("job_title"),
                "email": person.get("email"),
                "tags": sorted(person["_tags"]),
                "score": scored["score"],
                "reason": scored["reason"],
                "score_breakdown": scored["score_breakdown"],
            }
        )

    for category in buckets:
        buckets[category].sort(key=lambda x: x["score"], reverse=True)
        buckets[category] = buckets[category][:limit_per_category]

    return {c: buckets[c] for c in all_categories if c in wanted}
