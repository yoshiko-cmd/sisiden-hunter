"""Discord Webhookへの新着案件通知。

Botは使わない。Webhook URLへPOSTするだけなので常時起動が不要で、
収集を実行したときにだけ動く。LLM APIは使用しない。

通知に失敗しても収集処理そのものは止めない(要件34)。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests
import yaml

logger = logging.getLogger("sisiden.notify.discord")

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "config" / "notify.yaml"

# Discordの制限。1メッセージ10埋め込みまで、説明文は4096文字まで。
MAX_EMBEDS_PER_MESSAGE = 10
MAX_FIELD_LENGTH = 1024
REQUEST_TIMEOUT_SECONDS = 15

# 埋め込みの色(左端の帯)。ドキュメンタリー案件を目立たせる。
COLOR_DOCUMENTARY = 0xE8615A
COLOR_VIDEO = 0x4A90D9
COLOR_OTHER = 0x9B9B9B


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """通知設定を読み込む。設定ファイルが無ければ無効扱いにする。"""
    if not path.exists():
        return {"discord": {"enabled": False}}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"discord": {"enabled": False}}


def get_webhook_url(config: dict[str, Any] | None = None) -> str | None:
    """Webhook URLを取得する。

    環境変数 SISIDEN_DISCORD_WEBHOOK を優先する。設定ファイルに直接書く場合は
    そのファイルをGitにコミットしないこと(.gitignoreで除外済み)。
    """
    env_url = os.environ.get("SISIDEN_DISCORD_WEBHOOK")
    if env_url:
        return env_url.strip()

    config = config or load_config()
    discord = config.get("discord") or {}
    if not discord.get("enabled"):
        return None
    url = (discord.get("webhook_url") or "").strip()
    # 設定例のプレースホルダをそのまま使っている場合は未設定とみなす
    if not url or url.startswith("https://discord.com/api/webhooks/XXXX"):
        return None
    return url


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_embed(opportunity: dict[str, Any]) -> dict[str, Any]:
    """案件1件をDiscordの埋め込み形式に変換する。"""
    if opportunity.get("documentary_match"):
        color = COLOR_DOCUMENTARY
    elif opportunity.get("video_match"):
        color = COLOR_VIDEO
    else:
        color = COLOR_OTHER

    tags = []
    if opportunity.get("documentary_match"):
        tags.append("ドキュメンタリー")
    if opportunity.get("human_story_candidate"):
        tags.append("人が主人公にできる")
    if opportunity.get("project_story_candidate"):
        tags.append("プロジェクトが主人公にできる")
    for flag, label in [
        ("social_issue_match", "社会課題"),
        ("local_industry_match", "地域産業"),
        ("youth_match", "若者"),
        ("community_match", "地域"),
        ("education_match", "教育"),
    ]:
        if opportunity.get(flag):
            tags.append(label)

    place = " ".join(filter(None, [opportunity.get("prefecture"), opportunity.get("municipality")]))
    fields = [
        {
            "name": "発注機関",
            "value": _truncate(opportunity.get("organization_name") or "—", MAX_FIELD_LENGTH),
            "inline": True,
        },
        {"name": "地域", "value": place or "—", "inline": True},
        {"name": "スコア", "value": f"{opportunity.get('keyword_score', 0)}点", "inline": True},
    ]

    # API由来の日付は応募締切とは限らないため、そのことが伝わる表記にする
    if opportunity.get("application_deadline"):
        fields.append(
            {"name": "応募締切(確認済)", "value": opportunity["application_deadline"], "inline": True}
        )
    elif opportunity.get("api_tender_date"):
        fields.append(
            {
                "name": "API日付(要確認)",
                "value": f"{opportunity['api_tender_date']}\n※応募締切とは限りません",
                "inline": True,
            }
        )

    if opportunity.get("published_date"):
        fields.append({"name": "公告日", "value": opportunity["published_date"], "inline": True})

    if tags:
        fields.append({"name": "該当", "value": _truncate(" / ".join(tags), MAX_FIELD_LENGTH)})

    attachments = opportunity.get("attachment_urls") or []
    if attachments:
        fields.append({"name": "添付", "value": f"{len(attachments)}件(仕様書等)", "inline": True})

    embed: dict[str, Any] = {
        "title": _truncate(opportunity.get("project_name") or "(案件名なし)", 250),
        "color": color,
        "fields": fields,
        "footer": {"text": f"ID {opportunity.get('id')} · 官公需情報ポータル"},
    }
    if opportunity.get("external_url"):
        embed["url"] = opportunity["external_url"]
    return embed


def post_opportunities(
    opportunities: list[dict[str, Any]],
    *,
    webhook_url: str | None = None,
    summary: str | None = None,
    config: dict[str, Any] | None = None,
) -> bool:
    """新着案件をDiscordへ投稿する。

    戻り値: 投稿できたかどうか。失敗しても例外は投げない(収集を止めないため)。
    """
    config = config or load_config()
    webhook_url = webhook_url or get_webhook_url(config)
    if not webhook_url:
        logger.debug("Discord通知は未設定のためスキップします")
        return False
    if not opportunities:
        logger.debug("通知対象の新着案件がありません")
        return False

    # Discordは1メッセージあたり10埋め込みまで
    chunks = [
        opportunities[i : i + MAX_EMBEDS_PER_MESSAGE]
        for i in range(0, len(opportunities), MAX_EMBEDS_PER_MESSAGE)
    ]

    posted = False
    for i, chunk in enumerate(chunks):
        payload: dict[str, Any] = {"embeds": [build_embed(o) for o in chunk]}
        if i == 0 and summary:
            payload["content"] = summary

        try:
            resp = requests.post(webhook_url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            posted = True
        except requests.RequestException as exc:
            logger.error("Discordへの通知に失敗しました: %s", exc)
            return posted

    logger.info("Discordへ%d件を通知しました", len(opportunities))
    return posted


def select_notifiable(
    opportunities: list[dict[str, Any]], config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """通知対象を設定にもとづいて絞り込む。"""
    config = config or load_config()
    discord = config.get("discord") or {}
    min_score = discord.get("min_score", 1)
    documentary_only = discord.get("documentary_only", False)
    max_items = discord.get("max_items", 20)

    selected = [
        o
        for o in opportunities
        if o.get("keyword_score", 0) >= min_score
        and (not documentary_only or o.get("documentary_match"))
    ]
    selected.sort(
        key=lambda o: (bool(o.get("documentary_match")), o.get("keyword_score", 0)), reverse=True
    )
    return selected[:max_items]
