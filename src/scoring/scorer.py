"""ルールベースのキーワード判定・スコアリング(要件6〜10)。

AIは使用しない。実データ890件での検証結果をもとに、二段階方式を採用している。

  第1段階(anchor): 映像制作案件である裏付けがあるかを判定する
  第2段階(groups): 裏付けのある案件に対してのみ、テーマによる加点を行う

公告文(ProjectDescription)は入札説明書の全文であり、「中小企業者の受注機会確保」
「環境への配慮」といった定型文や、工事写真撮影・塗装の密着性といった専門用語を
含む。単純な全文一致では建設工事が軒並み満点になるため、裏付けの無い案件は
案件名のみを対象に低い上限で採点する。
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
    has_anchor: bool = False
    anchor_words: list[str] = field(default_factory=list)

    def to_db_dict(self) -> dict[str, int]:
        out = {flag: int(v) for flag, v in self.matches.items()}
        out["keyword_score"] = self.keyword_score
        out["human_story_candidate"] = int(self.human_story_candidate)
        out["project_story_candidate"] = int(self.project_story_candidate)
        return out


def _find_matches(text: str, words: list[str]) -> list[str]:
    lowered = (text or "").lower()
    return [w for w in words if w and w.lower() in lowered]


def find_anchor(title: str, body: str, keywords: dict) -> list[str]:
    """映像制作案件である裏付けとなる語を探す。

    strong は案件名・公告文・仕様書のどこにあっても有効。
    title_only は案件名にある場合のみ有効(公告文では定型文に紛れるため)。
    """
    anchor = keywords["anchor"]
    found = _find_matches(f"{title}\n{body}", anchor["strong"])
    found += _find_matches(title, anchor["title_only"])
    return sorted(set(found), key=len, reverse=True)


def score_fields(title: str, body: str = "", keywords: dict | None = None) -> ScoreResult:
    """案件名と本文を分けて採点する。"""
    keywords = keywords or load_keywords()
    title = title or ""
    body = body or ""

    anchor_words = find_anchor(title, body, keywords)
    has_anchor = bool(anchor_words)

    # 裏付けがあれば本文も採点対象にする。無ければ案件名のみを見る。
    # (公告文の定型文による誤加点を防ぐため)
    scoring_text = f"{title}\n{body}" if has_anchor else title
    max_score = 100 if has_anchor else keywords.get("no_anchor_max_score", 30)

    matches: dict[str, bool] = {}
    matched_words: dict[str, list[str]] = {}
    raw_score = 0

    for group_key, group_def in keywords["groups"].items():
        found = _find_matches(scoring_text, group_def["words"])
        flag_name = GROUP_TO_DB_FLAG.get(group_key, f"{group_key}_match")
        matches[flag_name] = bool(found)
        matched_words[group_key] = found
        if found:
            raw_score += group_def["score"]

    story = keywords["story_candidates"]
    human_story_candidate = bool(_find_matches(scoring_text, story["human_story"]["words"]))
    project_story_candidate = bool(_find_matches(scoring_text, story["project_story"]["words"]))

    # 業務の性質は案件名に表れるため、減点判定は案件名のみを見る。
    # (本文で「工事写真」に触れているだけの本物の映像案件を巻き添えにしないため)
    dep = keywords.get("deprioritize", {})
    dep_words_found = _find_matches(title, dep.get("words", []))
    if dep_words_found:
        raw_score -= dep.get("score_penalty", 0)
        # 式典記録・議会中継は「記録映像」に一致するが、ドキュメンタリー案件ではない。
        # ランキングはdocumentary_matchを最優先でソートするため、ここで落としておかないと
        # 本物のドキュメンタリー案件より上位に表示されてしまう。
        matches["documentary_match"] = False

    final_score = max(0, min(max_score, raw_score))

    return ScoreResult(
        keyword_score=final_score,
        matches=matches,
        matched_words=matched_words,
        human_story_candidate=human_story_candidate,
        project_story_candidate=project_story_candidate,
        deprioritized=bool(dep_words_found),
        deprioritize_words=dep_words_found,
        has_anchor=has_anchor,
        anchor_words=anchor_words,
    )


def score_text(text: str, keywords: dict | None = None) -> ScoreResult:
    """単一のテキストを採点する(案件名と本文を区別しない簡易版)。"""
    return score_fields(text, "", keywords)


def score_opportunity(record: dict) -> ScoreResult:
    """案件辞書から採点する。

    spec_text(添付仕様書から抽出した本文)が含まれる場合はそれも対象にする。
    案件名に「映像」と書かれていなくても、仕様書に「ドキュメンタリー」と
    書かれていれば裏付けとして検出される。
    """
    title = record.get("project_name") or ""
    body = "\n".join(
        [
            record.get("description") or "",
            record.get("category") or "",
            record.get("procedure_type") or "",
            record.get("spec_text") or "",
        ]
    )
    return score_fields(title, body)
