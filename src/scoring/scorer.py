"""ルールベースのキーワード判定・スコアリング(要件6〜10)。

AIは使用しない。案件名+公告本文(必要に応じ添付資料テキスト)に対して
キーワード一致を判定し、0-100のスコアと各種フラグを算出する。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .keywords import load_keywords

GROUP_TO_DB_FLAG = {
    "video": "video_match",
    "documentary": "documentary_match",
    "social_issue": "social_issue_match",
    "local_industry": "local_industry_match",
    "youth": "youth_match",
    "community": "community_match",
    "education": "education_match",
}


@dataclass
class ScoreResult:
    keyword_score: int
    matches: dict[str, bool] = field(default_factory=dict)          # DB flag name -> bool
    matched_words: dict[str, list[str]] = field(default_factory=dict)  # group -> matched words
    human_story_candidate: bool = False
    project_story_candidate: bool = False
    deprioritized: bool = False
    deprioritize_words: list[str] = field(default_factory=list)

    def to_db_dict(self) -> dict[str, int]:
        out = {flag: int(v) for flag, v in self.matches.items()}
        out["keyword_score"] = self.keyword_score
        out["human_story_candidate"] = int(self.human_story_candidate)
        out["project_story_candidate"] = int(self.project_story_candidate)
        return out


def _find_matches(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w and w.lower() in text.lower()]


def score_text(text: str, keywords: dict | None = None) -> ScoreResult:
    """案件名+本文などを結合したテキストに対してスコアを計算する。"""
    keywords = keywords or load_keywords()
    text = text or ""

    matches: dict[str, bool] = {}
    matched_words: dict[str, list[str]] = {}
    raw_score = 0

    for group_key, group_def in keywords["groups"].items():
        found = _find_matches(text, group_def["words"])
        flag_name = GROUP_TO_DB_FLAG.get(group_key, f"{group_key}_match")
        matches[flag_name] = bool(found)
        matched_words[group_key] = found
        if found:
            raw_score += group_def["score"]

    story = keywords["story_candidates"]
    human_story_candidate = bool(_find_matches(text, story["human_story"]["words"]))
    project_story_candidate = bool(_find_matches(text, story["project_story"]["words"]))

    dep = keywords.get("deprioritize", {})
    dep_words_found = _find_matches(text, dep.get("words", []))
    deprioritized = bool(dep_words_found)
    if deprioritized:
        raw_score -= dep.get("score_penalty", 0)

    # ドキュメンタリー明記案件は原則最優先候補とする(要件7)
    final_score = max(0, min(100, raw_score))

    return ScoreResult(
        keyword_score=final_score,
        matches=matches,
        matched_words=matched_words,
        human_story_candidate=human_story_candidate,
        project_story_candidate=project_story_candidate,
        deprioritized=deprioritized,
        deprioritize_words=dep_words_found,
    )


def score_opportunity(record: dict) -> ScoreResult:
    """案件辞書からスコアリング対象テキストを構成して判定する。

    spec_text(添付仕様書から抽出した本文)が含まれる場合はそれも対象にする。
    案件名に「映像」と書かれていなくても、仕様書に「ドキュメンタリー」と
    書かれている案件を検出するため。
    """
    parts = [
        record.get("project_name") or "",
        record.get("description") or "",
        record.get("category") or "",
        record.get("procedure_type") or "",
        record.get("spec_text") or "",
    ]
    text = "\n".join(parts)
    return score_text(text)
