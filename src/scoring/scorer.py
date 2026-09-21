"""ルールベースのキーワード判定・スコアリング(要件6〜10)。

AIは使用しない。実データでの検証を2回行い、採点対象そのものを見直した。

■ 1回目の検証(890件)で判明したこと
  公告文の全文に対する単純なキーワード一致では建設工事が軒並み95〜100点になった。
  「密着」は塗装の密着性・密着造林型、「撮影」は工事写真撮影として頻出し、
  「中小企業」「環境」「災害」は官公需の公告文の定型文に必ず含まれるため。
  → 映像案件である裏付け(anchor)を必須とする二段階方式にした。

■ 2回目の検証で判明したこと(より根本的)
  APIのProjectDescriptionは、その案件だけの文章とは限らない。
  発注機関によっては「他の案件も並んだ一覧ページ全体」が入っている。
  実際、宮崎県の無線LAN構築・防災ネットワーク保守・パスポート輸送が
  揃って同じ点数になった。同じページを共有しており、そこに映像案件が
  1件でも含まれていたため全件が映像案件と誤認された。
  → 公告文は採点にもanchor判定にも使わない。

■ 現在の採点対象
  案件名(ProjectName)     … その案件固有。第一の信号。
  仕様書本文(spec_text)   … 添付PDFから抽出。その案件固有。裏付けの確証。
  公告文(description)     … 汚染されうるため採点に使わない(検索・表示には残す)

  「案件名で見つけ、仕様書で確かめる」という流れになる。
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
    anchor_source: str | None = None  # "title" | "spec" | None

    def to_db_dict(self) -> dict[str, int]:
        out = {flag: int(v) for flag, v in self.matches.items()}
        out["keyword_score"] = self.keyword_score
        out["human_story_candidate"] = int(self.human_story_candidate)
        out["project_story_candidate"] = int(self.project_story_candidate)
        return out


def _find_matches(text: str, words: list[str]) -> list[str]:
    lowered = (text or "").lower()
    return [w for w in words if w and w.lower() in lowered]


def find_anchor(title: str, spec_text: str, keywords: dict) -> tuple[list[str], str | None]:
    """映像制作案件である裏付けを探す。

    案件名と仕様書本文のみを見る。公告文は他案件の文章を含みうるため使わない。

    戻り値: (裏付けとなった語, 由来("title"|"spec"|None))
    """
    anchor = keywords["anchor"]

    title_found = _find_matches(title, anchor["strong"]) + _find_matches(title, anchor["title_only"])
    if title_found:
        return sorted(set(title_found), key=len, reverse=True), "title"

    # 仕様書本文はその案件固有なので、strongな語であれば裏付けとして認める。
    # (案件名に映像と無くても、仕様書にドキュメンタリーと書かれている案件を拾うため)
    spec_found = _find_matches(spec_text, anchor["strong"])
    if spec_found:
        return sorted(set(spec_found), key=len, reverse=True), "spec"

    return [], None


def score_fields(
    title: str,
    spec_text: str = "",
    description: str = "",
    keywords: dict | None = None,
) -> ScoreResult:
    """案件を採点する。

    title      … 案件名。その案件固有の情報。
    spec_text  … 添付仕様書から抽出した本文。その案件固有の情報。
    description… 公告文。一覧ページ全体である場合があるため採点に使わない。
                 引数として受け取るのは、呼び出し側の意図を明示するため。
    """
    keywords = keywords or load_keywords()
    title = title or ""
    spec_text = spec_text or ""

    anchor_words, anchor_source = find_anchor(title, spec_text, keywords)
    has_anchor = bool(anchor_words)

    # 裏付けがあれば仕様書本文も加点対象にする。無ければ案件名のみ。
    scoring_text = f"{title}\n{spec_text}" if has_anchor else title
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

    # 裏付けの語は、それ自体が映像案件である証拠。
    # 「ショートドラマ制作」「エンドロール制作」のように加点用キーワードには
    # 無い表現でも、裏付けが取れた以上は映像案件として加点する。
    if has_anchor and not matches["video_match"]:
        matches["video_match"] = True
        matched_words["video"] = anchor_words
        raw_score += keywords["groups"]["video"]["score"]

    story = keywords["story_candidates"]
    human_story_candidate = bool(_find_matches(scoring_text, story["human_story"]["words"]))
    project_story_candidate = bool(_find_matches(scoring_text, story["project_story"]["words"]))

    # 業務の性質は案件名に表れるため、減点判定は案件名のみを見る。
    dep = keywords.get("deprioritize", {})
    dep_words_found = _find_matches(title, dep.get("words", []))
    if dep_words_found:
        raw_score -= dep.get("score_penalty", 0)
        # 式典記録・議会中継は「記録映像」に一致するがドキュメンタリー案件ではない。
        # ランキングはdocumentary_matchを最優先でソートするため、ここで落としておく。
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
        anchor_source=anchor_source,
    )


def score_text(text: str, keywords: dict | None = None) -> ScoreResult:
    """単一のテキストを案件名として採点する(簡易版)。"""
    return score_fields(text, keywords=keywords)


def score_opportunity(record: dict) -> ScoreResult:
    """案件辞書から採点する。

    公告文(description)は採点に使わない。APIのProjectDescriptionには
    他の案件も並んだ一覧ページ全体が入っていることがあるため。
    """
    return score_fields(
        title=record.get("project_name") or "",
        spec_text=record.get("spec_text") or "",
        description=record.get("description") or "",
    )
