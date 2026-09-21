#!/usr/bin/env python3
"""SISIDEN Relationship OS MCP Server。

「名刺は名刺として保存しない。人との関係を会社の資産にする。
 プレスリリースは配信して終わりにしない。
 営業と広報を別部署の仕事として設計しない。」

このMCPは、株式会社シシクリエイションが持つ人脈(名刺交換した人・記者・自治体関係者・
顧客・パートナー等)・案件(SISIDENのProject)・接点履歴(Interaction)を1つの
人物中心DBとして扱い、Claudeが自然言語で「この案件を誰に届けるべきか」を
判断できるようにする。

自治体案件ハンター(src/mcp/server.py)とは別プロセスのMCPサーバーとして動作する
(データの性質が異なるため: 案件探索 vs 人脈・PR・営業のリレーションシップ管理)。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer

from src.relationship.mcp import tools

INSTRUCTIONS = """\
このMCPはSISIDEN Relationship OS(株式会社シシクリエイションの人脈・メディア・案件管理)です。

基本思想:
- 中心にあるのは「会社」ではなく「人物」。人物 → 所属組織 → 過去の接点 → 興味関心 →
  関連案件 → 送った情報 → 反応、を追える。
- 「広報」と「営業」を分離しない。1人の人物が「過去の取材先」「企業広報」「見込み顧客」
  「イベント参加者」を同時に兼ねることがある。
- 名刺やメールのやり取りは「保存して終わり」ではなく、次に何を届けるべきかを判断する
  ための資産として扱う。

あなた(Claude)の役割:
- search_people / search_organizations / recommend_people_for_project 等で
  ルールベースの検索・スコアリング結果を取得し、それを踏まえて自然言語で説明・判断する。
- 記者向けPitch文、SISIDEN LETTER、営業メール、SISIDEN Web記事などの「文章生成」は
  あなたの仕事です。このMCPサーバー自体は文章生成も外部送信も行いません
  (ルールベースの検索・集計に徹底しています)。
- 検索結果を提示するときは、人物名だけでなく「なぜこの人が候補なのか」を
  reasonフィールドの内容を使って必ず説明してください。

厳守事項:
- 外部送信(記者への情報提供・営業メール・メルマガ配信・イベント招待)は、
  必ず人間の最終承認を経てください。このMCPには送信機能自体が存在しません。
  update_campaign_target_status(status="approved"→"sent") は「人間が承認・送信した事実の記録」
  であり、あなたが勝手にsentへ進めてはいけません。
- newsletter_status / sales_email_status / media_pitch_status が
  'unsubscribed' または 'do_not_contact' の人物は、recommend_people_for_project の
  候補から自動的に除外されます。あなたが個別にこれを回避してはいけません。

典型的な使い方:
- 「TONKANの公開を知らせるべき人を出して」
  → search_projects(text="TONKAN") → recommend_people_for_project(project_id=...)
- 「名刺交換した人の中から地方創生に関心がありそうな人を出して」
  → search_people(source="eight", tags=["地方創生"])
- 「過去1年間連絡していない見込み顧客を出して」
  → search_people(tags=["見込み顧客"], not_contacted_since_days=365)
- 「過去に返信があった記者だけ出して」
  → search_people(is_media=True, has_reply=True)
- 「この人と最後に何の話をした？」→ get_person(id=...) の recent_interactions を見る
- 「この会社に誰と接点がある？」→ get_organization(id=...) の persons を見る
- 案件登録の流れ(STEP1〜8): create_project → recommend_people_for_project →
  create_campaign → add_campaign_audience → (あなたが文面案を作成) →
  add_campaign_targets(draft_textを含めて登録) → 人間が確認 →
  update_campaign_target_status(status="approved"→"sent") → Interactionは自動記録される
"""

mcp = MCPServer(
    name="sisiden-relationship-os",
    instructions=INSTRUCTIONS,
)


# ============================================================
# PERSON
# ============================================================

@mcp.tool(description="人物を検索する。自由文検索(text)、タグ、組織タイプ、業界、地域、役職、情報源、記者/編集者限定(is_media)、関係性強度、未接触日数、直近接触日数、返信有無、オプトアウト状態などで絞り込み可能。自然言語の質問はこの条件に変換して呼び出すこと。")
def search_people(
    text: str | None = None,
    tags: list[str] | None = None,
    match_all_tags: bool = False,
    organization_type: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    job_title_contains: str | None = None,
    source: str | None = None,
    is_media: bool | None = None,
    min_relationship_strength: int | None = None,
    not_contacted_since_days: int | None = None,
    contacted_within_days: int | None = None,
    has_reply: bool | None = None,
    newsletter_status: str | None = None,
    sales_email_status: str | None = None,
    media_pitch_status: str | None = None,
    contactable_for: str | None = None,
    limit: int = 50,
) -> dict:
    return tools.search_people(
        text=text,
        tags=tags,
        match_all_tags=match_all_tags,
        organization_type=organization_type,
        industry=industry,
        location=location,
        job_title_contains=job_title_contains,
        source=source,
        is_media=is_media,
        min_relationship_strength=min_relationship_strength,
        not_contacted_since_days=not_contacted_since_days,
        contacted_within_days=contacted_within_days,
        has_reply=has_reply,
        newsletter_status=newsletter_status,
        sales_email_status=sales_email_status,
        media_pitch_status=media_pitch_status,
        contactable_for=contactable_for,
        limit=limit,
    )


@mcp.tool(description="人物IDを指定して詳細(所属組織、タグ、記者プロフィール、直近の接点履歴20件、オプトアウト状態)を取得する。「この人と最後に何の話をした?」等に使う。")
def get_person(id: int) -> dict:
    return tools.get_person(id)


@mcp.tool(description="人物を新規登録する(手入力用)。メールアドレスが既存人物と一致する場合は自動的に既存人物を更新し、電話番号/氏名+会社名/氏名+部署の一致は重複候補として記録される(自動統合はしない)。fieldsにはname(必須)/name_kana/email/phone/organization_id/organization_name/department/job_title/location/source/first_met_at/first_met_context/notesを指定できる。")
def create_person(fields: dict) -> dict:
    return tools.create_person(fields)


@mcp.tool(description="人物のオプトアウト状態を設定する。channelは newsletter/sales/media_pitch のいずれか、statusは 許可側(subscribed/allowed)/unsubscribed/do_not_contact。do_not_contactになった人物は候補抽出から必ず除外される。")
def set_optout(person_id: int, channel: str, status: str) -> dict:
    return tools.set_optout(person_id, channel, status)


@mcp.tool(description="人物を記者・編集者として登録/更新する(media_profile)。fieldsにはoutlet_name/genre/area/interest_themes/past_article_urls/last_contacted_at/reply_notesを指定できる。呼ぶと自動的に「メディア」タグが付与される。")
def update_media_profile(person_id: int, fields: dict) -> dict:
    return tools.update_media_profile(person_id, fields)


# ============================================================
# ORGANIZATION
# ============================================================

@mcp.tool(description="組織(企業・自治体・学校・大学・媒体・団体)を検索する。")
def search_organizations(
    text: str | None = None,
    org_type: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    limit: int = 50,
) -> dict:
    return tools.search_organizations(text=text, org_type=org_type, industry=industry, location=location, limit=limit)


@mcp.tool(description="組織IDを指定して詳細と、その組織に所属する人物一覧を取得する。「この会社に誰と接点がある?」に使う。")
def get_organization(id: int) -> dict:
    return tools.get_organization(id)


# ============================================================
# PROJECT
# ============================================================

@mcp.tool(description="SISIDEN案件を新規登録する(案件登録フローのSTEP1)。fieldsにはproject_name(必須)/client/description/status/release_date/location/main_theme/social_issue/industry/keywords(配列)/target_audience/related_url/video_url/article_urlを指定できる。")
def create_project(fields: dict) -> dict:
    return tools.create_project(fields)


@mcp.tool(description="案件IDを指定して詳細(掲載実績・コンテンツ一覧を含む)を取得する。")
def get_project(id: int) -> dict:
    return tools.get_project(id)


@mcp.tool(description="案件を自由文・ステータスで検索する。「TONKANの案件」のような呼びかけはまずこれで案件IDを特定する。")
def search_projects(text: str | None = None, status: str | None = None, limit: int = 30) -> dict:
    return tools.search_projects(text=text, status=status, limit=limit)


@mcp.tool(description="案件に対する人物候補をMEDIA(取材・掲載候補)/SALES(営業候補)/RELATIONSHIP(近況共有候補)/AMPLIFICATION(拡散・紹介依頼候補)に分類して抽出する(案件登録フローのSTEP2〜4)。各候補にはルールベースで計算したscore(0-100)と、なぜ候補なのかを説明するreasonが必ず付く。オプトアウト済みの人物は自動的に除外される。categoriesを指定すると特定カテゴリのみ抽出できる。")
def recommend_people_for_project(
    project_id: int,
    categories: list[str] | None = None,
    limit_per_category: int = 10,
    min_score: int = 15,
) -> dict:
    return tools.recommend_people_for_project(
        project_id, categories=categories, limit_per_category=limit_per_category, min_score=min_score
    )


# ============================================================
# INTERACTION
# ============================================================

@mcp.tool(description="接点(Interaction)を1件記録する。名刺交換・メール・面談・電話・イベント・メルマガ・記者へのPitch・SNS・紹介などすべての接触を資産化するために使う。fieldsにはperson_id(必須)/project_id/date(必須,YYYY-MM-DD)/channel(必須: email/meeting/business_card/phone/event/newsletter/media_pitch/sns/introduction)/direction(inbound/outbound)/subject/summary/reaction/next_action/next_action_dateを指定できる。")
def log_interaction(fields: dict) -> dict:
    return tools.log_interaction(fields)


# ============================================================
# CAMPAIGN (案件登録フローSTEP5〜8)
# ============================================================

@mcp.tool(description="Campaign(情報発信の単位)を作成する。fieldsにはname(必須)/project_id/campaign_type(media/sales/relationship/amplification/newsletter/mixed)/status/start_date/end_date/notesを指定できる。")
def create_campaign(fields: dict) -> dict:
    return tools.create_campaign(fields)


@mcp.tool(description="Campaignに配信対象セグメント(例:「記者向け」「名刺交換者」「大学」「自治体」「SNS」)を追加する。filter_jsonには抽出に使った検索条件をJSON文字列で保存すると再現性が保てる。")
def add_campaign_audience(campaign_id: int, audience_label: str, filter_json: str | None = None) -> dict:
    return tools.add_campaign_audience(campaign_id, audience_label, filter_json)


@mcp.tool(description="recommend_people_for_projectの結果の中から人間が選んだ対象をCampaignへ登録する(STEP6の前段)。targetsは各要素が{person_id, category, score, reason, draft_text}の配列。draft_textにはあなたが生成した文面案を入れてよい(この時点ではまだ送信されない)。")
def add_campaign_targets(campaign_id: int, targets: list[dict], audience_id: int | None = None) -> dict:
    return tools.add_campaign_targets(campaign_id, targets, audience_id=audience_id)


@mcp.tool(description="Campaignの対象者一覧を取得する。")
def list_campaign_targets(campaign_id: int, category: str | None = None, status: str | None = None) -> dict:
    return tools.list_campaign_targets(campaign_id, category=category, status=status)


@mcp.tool(description="Campaign対象者のステータスを更新する(candidate/approved/rejected/sent)。重要: statusを'sent'にするのは、人間が実際に送信を完了した後にその事実を記録するときだけ。sentにすると対応するInteractionが自動的に1件記録される(STEP8)。このツール自体はメールや通知を送信しない。")
def update_campaign_target_status(
    campaign_target_id: int,
    status: str,
    approved_by: str | None = None,
    draft_text: str | None = None,
) -> dict:
    return tools.update_campaign_target_status(
        campaign_target_id, status, approved_by=approved_by, draft_text=draft_text
    )


# ============================================================
# COVERAGE
# ============================================================

@mcp.tool(description="メディア掲載実績を記録する。fieldsにはproject_id/person_id(記者)/organization_id(媒体)/published_date/outlet_name/url/triggered_by_interaction_id(きっかけとなったPitchのInteraction ID)/notesを指定できる。")
def record_coverage(fields: dict) -> dict:
    return tools.record_coverage(fields)


# ============================================================
# 重複候補の確認(人間確認フロー)
# ============================================================

@mcp.tool(description="確信度の低い重複候補(電話番号/氏名+会社名/氏名+部署が一致したが自動統合されなかった人物ペア)の一覧を取得する。人間が確認して resolve_duplicate で統合/却下を判断する。")
def list_duplicate_candidates(status: str = "pending", limit: int = 50) -> dict:
    return tools.list_duplicate_candidates(status=status, limit=limit)


@mcp.tool(description="重複候補を解決する。action='merge'で統合(keep_person_idを指定しない場合は先に登録された方を残す)、action='reject'で「別人」として却下する。統合は必ず人間の確認結果として呼び出すこと。")
def resolve_duplicate(duplicate_id: int, action: str, keep_person_id: int | None = None, resolved_by: str | None = None) -> dict:
    return tools.resolve_duplicate(duplicate_id, action, keep_person_id=keep_person_id, resolved_by=resolved_by)


# ============================================================
# DASHBOARD
# ============================================================

@mcp.tool(description="ダッシュボード情報を取得する: 進行中Project、今後7日以内のフォローアップ予定、関係性強度が高いのに180日以上連絡していない重要人物、最近返信があった人物、最近のメディア掲載、今月のCampaign、未解決の重複候補件数。")
def get_dashboard() -> dict:
    return tools.get_dashboard()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
