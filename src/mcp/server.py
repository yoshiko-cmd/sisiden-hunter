#!/usr/bin/env python3
"""SISIDEN 全国自治体案件ハンター MCP Server (要件14〜20)。

特定のMCPクライアント(Claude Desktop/Claude Code/ChatGPT/Codex等)に依存せず、
標準のMCP(Model Context Protocol)のみに依存する設計。
デフォルトはSTDIOトランスポートだが、run(transport="streamable-http")で
将来的にHTTPへ移行できる。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer

from src.mcp import tools

INSTRUCTIONS = """\
このMCPは株式会社シシクリエイションの自治体・官公庁案件探索用です。
SISIDENは単なる映像制作ではなく、人・地域・社会課題・プロジェクトの物語を
第三者視点のドキュメンタリーとして伝える事業です。
案件選定では映像制作案件を最優先し、ドキュメンタリー明記案件を特に優先してください。
また、社会課題、地域産業、若者、人を主人公にできる案件、プロジェクトを主人公にできる案件、
物語性のある案件を高く評価してください。
広告PV・式典記録・単純撮影のみの案件は優先度を下げてください。

このサーバーの一次収集・スコアリングはルールベースで行われています(AI不使用)。
高度な判断(主人公性の最終判定、提案戦略の検討)はあなた(MCPクライアント)が
案件データ・仕様書を読んだ上で行ってください。
"""

mcp = MCPServer(
    name="sisiden-opportunity-mcp",
    instructions=INSTRUCTIONS,
)


@mcp.tool(description="全国の自治体・官公庁案件を条件で検索する。都道府県、月、スコア下限、キーワード、映像/ドキュメンタリー限定、ステータス等で絞り込み可能。")
def search_opportunities(
    prefecture: str | None = None,
    municipality: str | None = None,
    month: str | None = None,
    published_from: str | None = None,
    published_to: str | None = None,
    deadline_from: str | None = None,
    deadline_to: str | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    keywords: list[str] | None = None,
    video_only: bool = False,
    documentary_only: bool = False,
    youth_only: bool = False,
    social_issue_only: bool = False,
    local_industry_only: bool = False,
    human_story_candidate: bool | None = None,
    project_story_candidate: bool | None = None,
    status: str | None = None,
    limit: int = 30,
) -> dict:
    return tools.search_opportunities(
        prefecture=prefecture,
        municipality=municipality,
        month=month,
        published_from=published_from,
        published_to=published_to,
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        min_score=min_score,
        max_score=max_score,
        keywords=keywords,
        video_only=video_only,
        documentary_only=documentary_only,
        youth_only=youth_only,
        social_issue_only=social_issue_only,
        local_industry_only=local_industry_only,
        human_story_candidate=human_story_candidate,
        project_story_candidate=project_story_candidate,
        status=status,
        limit=limit,
    )


@mcp.tool(description="案件IDを指定して詳細情報(発注元・日程・URL・本文・添付資料一覧・スコア・各種フラグ・ステータス・メモ)を取得する。")
def get_opportunity(id: int) -> dict:
    return tools.get_opportunity(id)


@mcp.tool(description="案件IDを指定し、添付されている仕様書・公募要項等のPDFをダウンロードして取得する。")
def get_specification(id: int) -> dict:
    return tools.get_specification(id)


@mcp.tool(description="案件のステータス(new/reviewing/candidate/proposal/applied/won/lost/ignored/expired)やメモ、優先度をユーザー判断として保存する。")
def update_opportunity_status(
    id: int,
    status: str | None = None,
    memo: str | None = None,
    user_priority: int | None = None,
) -> dict:
    return tools.update_opportunity_status(id, status=status, memo=memo, user_priority=user_priority)


@mcp.tool(description="SISIDEN向けランキング(ドキュメンタリー明記 > キーワードスコア > 締切までの日数 > 新着順)で上位案件を表示する。")
def list_top_opportunities(
    period: str | None = None,
    prefecture: str | None = None,
    limit: int = 20,
) -> dict:
    return tools.list_top_opportunities(period=period, prefecture=prefecture, limit=limit)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
