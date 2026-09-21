-- SISIDEN Relationship OS DBスキーマ
-- 「営業」と「広報」を分離せず、人物(PERSON)を中心にすべての関係を統合するDB。
-- MVP: SQLite。将来のPostgreSQL移行を想定し、SQLite固有記法(AUTOINCREMENT以外)は避ける。
-- 既存の sisiden_opportunities.db (自治体案件ハンター) とは別ファイルで運用する。

-- ============================================================
-- ORGANIZATION: 会社・自治体・学校・団体・媒体を統合管理
-- ============================================================
CREATE TABLE IF NOT EXISTS organizations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    name_kana           TEXT,
    type                TEXT NOT NULL DEFAULT 'other',   -- company/municipality/school/university/media/ngo/association/other
    industry            TEXT,
    website             TEXT,
    location            TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_organizations_name ON organizations(name);
CREATE INDEX IF NOT EXISTS idx_organizations_type ON organizations(type);

-- ============================================================
-- PERSON: 人物中心DBの核。名刺・メール・過去案件・反応まで、この人物に紐づく。
-- ============================================================
CREATE TABLE IF NOT EXISTS persons (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT NOT NULL,
    name_kana               TEXT,
    email                   TEXT,                          -- 重複判定の最優先キー(正規化済み: lower/trim)
    email_secondary         TEXT,
    phone                   TEXT,                          -- 正規化済み(数字のみ)
    organization_id         INTEGER REFERENCES organizations(id),
    department              TEXT,
    job_title               TEXT,
    location                TEXT,
    source                  TEXT NOT NULL DEFAULT 'manual', -- eight/gmail/csv_sales/csv_media/manual
    source_id               TEXT,                            -- 出所側の識別子(取得できる場合)
    first_met_at            TEXT,                            -- いつ出会ったか
    first_met_context       TEXT,                            -- どこで/なぜ出会ったか
    last_contact_at         TEXT,                            -- 直近接触日(Interaction保存時に更新)
    relationship_strength   INTEGER NOT NULL DEFAULT 0,      -- 0-100(ルールベースで加点、手動調整可)

    -- オプトアウト管理(削除せず、送信禁止情報として保持する)
    newsletter_status       TEXT NOT NULL DEFAULT 'subscribed',   -- subscribed/unsubscribed/do_not_contact
    sales_email_status      TEXT NOT NULL DEFAULT 'allowed',      -- allowed/unsubscribed/do_not_contact
    media_pitch_status      TEXT NOT NULL DEFAULT 'allowed',      -- allowed/unsubscribed/do_not_contact

    notes                   TEXT,
    merged_into_id          INTEGER REFERENCES persons(id),  -- 重複統合で吸収された場合の統合先(監査用)
    is_deleted              INTEGER NOT NULL DEFAULT 0,      -- 論理削除(本人からの削除依頼等)
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_persons_email ON persons(email);
CREATE INDEX IF NOT EXISTS idx_persons_phone ON persons(phone);
CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(name);
CREATE INDEX IF NOT EXISTS idx_persons_organization_id ON persons(organization_id);
CREATE INDEX IF NOT EXISTS idx_persons_last_contact_at ON persons(last_contact_at);
CREATE INDEX IF NOT EXISTS idx_persons_is_deleted ON persons(is_deleted);

-- 人物がどの情報源(複数可)から取り込まれたかの履歴。同一人物が複数ソースを持てる。
CREATE TABLE IF NOT EXISTS person_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id       INTEGER NOT NULL REFERENCES persons(id),
    source          TEXT NOT NULL,          -- eight/gmail/csv_sales/csv_media/manual
    source_id       TEXT,
    imported_at     TEXT NOT NULL DEFAULT (datetime('now')),
    import_batch_id INTEGER REFERENCES import_batches(id)
);
CREATE INDEX IF NOT EXISTS idx_person_sources_person_id ON person_sources(person_id);

-- ============================================================
-- TAG: 人物・案件に複数付けられる関心・属性タグ
-- ============================================================
CREATE TABLE IF NOT EXISTS tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    category    TEXT,                        -- role/industry/theme/eight_tag/other
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS person_tags (
    person_id   INTEGER NOT NULL REFERENCES persons(id),
    tag_id      INTEGER NOT NULL REFERENCES tags(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (person_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_person_tags_tag_id ON person_tags(tag_id);

-- ============================================================
-- MEDIA_PROFILE: PERSONが記者・編集者等の場合の追加情報(1人物1プロフィール)
-- ============================================================
CREATE TABLE IF NOT EXISTS media_profiles (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id               INTEGER NOT NULL UNIQUE REFERENCES persons(id),
    outlet_name             TEXT,             -- 媒体名(organizationと重複してよい。表記ゆれ吸収用)
    genre                   TEXT,             -- 担当ジャンル
    area                    TEXT,             -- 担当エリア
    interest_themes         TEXT,             -- 興味テーマ(自由記述/カンマ区切り)
    past_article_urls       TEXT,             -- JSON配列 [{title,url,date}]
    past_pitched_projects   TEXT,             -- JSON配列(project_idのリスト)
    last_contacted_at       TEXT,
    reply_notes             TEXT,             -- 返信・反応の傾向メモ
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- PROJECT: SISIDEN案件DB
-- ============================================================
CREATE TABLE IF NOT EXISTS projects (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name        TEXT NOT NULL,
    client              TEXT,
    description         TEXT,
    status              TEXT NOT NULL DEFAULT 'planning',  -- planning/in_production/released/archived
    release_date        TEXT,
    location             TEXT,
    main_theme           TEXT,
    social_issue          TEXT,
    industry               TEXT,
    keywords                TEXT,              -- JSON配列(テーマ一致計算に使う)
    target_audience          TEXT,
    related_url                TEXT,
    video_url                   TEXT,
    article_url                  TEXT,
    opportunity_id                 INTEGER,    -- 自治体案件ハンターDB(別ファイル)のopportunities.idへの参照(FK制約なし)
    created_at                       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

-- ============================================================
-- INTERACTION: すべての接触履歴(名刺交換・メール・イベント等)を資産化する
-- ============================================================
CREATE TABLE IF NOT EXISTS interactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id           INTEGER NOT NULL REFERENCES persons(id),
    project_id          INTEGER REFERENCES projects(id),
    date                TEXT NOT NULL,
    channel             TEXT NOT NULL,   -- email/meeting/business_card/phone/event/newsletter/media_pitch/sns/introduction
    direction            TEXT NOT NULL DEFAULT 'outbound',  -- inbound/outbound
    subject               TEXT,
    summary                TEXT,
    reaction                TEXT,          -- 返信内容・反応の要約
    next_action               TEXT,
    next_action_date            TEXT,
    campaign_id                  INTEGER REFERENCES campaigns(id),
    created_by                    TEXT,      -- 記録した担当者
    created_at                     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_interactions_person_id ON interactions(person_id);
CREATE INDEX IF NOT EXISTS idx_interactions_project_id ON interactions(project_id);
CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(date);
CREATE INDEX IF NOT EXISTS idx_interactions_next_action_date ON interactions(next_action_date);

-- ============================================================
-- CAMPAIGN: 情報発信の単位(1 Projectから複数Audienceへ展開)
-- ============================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    project_id      INTEGER REFERENCES projects(id),
    campaign_type   TEXT NOT NULL DEFAULT 'mixed',  -- media/sales/relationship/amplification/newsletter/mixed
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft/active/completed
    start_date      TEXT,
    end_date        TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_campaigns_project_id ON campaigns(project_id);

-- Campaignごとの配信対象セグメント(記者向け/名刺交換者/大学/自治体/SNS等)
CREATE TABLE IF NOT EXISTS campaign_audiences (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id         INTEGER NOT NULL REFERENCES campaigns(id),
    audience_label       TEXT NOT NULL,   -- 例: "記者向け","名刺交換者","大学","自治体","SNS"
    filter_json            TEXT,           -- 抽出に使ったフィルタ条件(JSON、再現性のため保存)
    created_at               TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Campaignごとの対象人物(候補抽出→分類→人間承認→送信→Interaction化の中心テーブル)
CREATE TABLE IF NOT EXISTS campaign_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id     INTEGER NOT NULL REFERENCES campaigns(id),
    audience_id     INTEGER REFERENCES campaign_audiences(id),
    person_id       INTEGER NOT NULL REFERENCES persons(id),
    category        TEXT NOT NULL,   -- MEDIA/SALES/RELATIONSHIP/AMPLIFICATION
    score           INTEGER,          -- マッチングスコア(0-100)
    reason          TEXT,              -- なぜこの人が候補なのか(文章)
    status          TEXT NOT NULL DEFAULT 'candidate',  -- candidate/approved/rejected/sent
    draft_text      TEXT,               -- Claudeが生成した文面案(承認前)
    approved_by     TEXT,
    approved_at     TEXT,
    sent_at         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (campaign_id, person_id)
);
CREATE INDEX IF NOT EXISTS idx_campaign_targets_campaign_id ON campaign_targets(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_targets_person_id ON campaign_targets(person_id);
CREATE INDEX IF NOT EXISTS idx_campaign_targets_status ON campaign_targets(status);

-- ============================================================
-- CONTENT: 発信に使うコンテンツ(SISIDEN映像/Web記事/上映会/SNS等)
-- ============================================================
CREATE TABLE IF NOT EXISTS contents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER REFERENCES projects(id),
    content_type    TEXT NOT NULL,   -- video/article/news/interview/screening/talk/press/sns/case_study
    title           TEXT NOT NULL,
    url             TEXT,
    published_date  TEXT,
    summary         TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_contents_project_id ON contents(project_id);

-- ============================================================
-- COVERAGE: メディア掲載実績
-- ============================================================
CREATE TABLE IF NOT EXISTS coverage (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                  INTEGER REFERENCES projects(id),
    person_id                   INTEGER REFERENCES persons(id),        -- 掲載してくれた記者
    organization_id              INTEGER REFERENCES organizations(id),  -- 媒体
    published_date                TEXT,
    outlet_name                     TEXT,
    url                                TEXT,
    triggered_by_interaction_id         INTEGER REFERENCES interactions(id), -- きっかけとなったPitch
    notes                                 TEXT,
    created_at                             TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_coverage_project_id ON coverage(project_id);
CREATE INDEX IF NOT EXISTS idx_coverage_person_id ON coverage(person_id);

-- ============================================================
-- DUPLICATE_CANDIDATES: 確信度の低い重複候補(人間の確認待ち)
-- ============================================================
CREATE TABLE IF NOT EXISTS duplicate_candidates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id_a     INTEGER NOT NULL REFERENCES persons(id),
    person_id_b     INTEGER NOT NULL REFERENCES persons(id),
    match_basis     TEXT NOT NULL,    -- email/phone/name_org/name_dept
    confidence      TEXT NOT NULL,    -- high/medium/low
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending/merged/rejected
    detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT,
    resolved_by     TEXT,
    UNIQUE (person_id_a, person_id_b, match_basis)
);
CREATE INDEX IF NOT EXISTS idx_duplicate_candidates_status ON duplicate_candidates(status);

-- ============================================================
-- IMPORT_BATCHES: CSVインポートの監査ログ
-- ============================================================
CREATE TABLE IF NOT EXISTS import_batches (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    source                      TEXT NOT NULL,   -- eight/csv_sales/csv_media/manual
    file_name                    TEXT,
    imported_at                    TEXT NOT NULL DEFAULT (datetime('now')),
    total_rows                       INTEGER NOT NULL DEFAULT 0,
    new_persons                       INTEGER NOT NULL DEFAULT 0,
    matched_persons                    INTEGER NOT NULL DEFAULT 0,
    duplicate_candidates_created         INTEGER NOT NULL DEFAULT 0,
    errors_json                            TEXT,
    note                                     TEXT
);
