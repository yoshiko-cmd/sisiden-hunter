-- SISIDEN 全国自治体案件ハンター DBスキーマ
-- MVP: SQLite。将来のPostgreSQL移行を想定し、SQLite固有記法(AUTOINCREMENT以外)は避ける。

CREATE TABLE IF NOT EXISTS opportunities (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 出所・識別
    source                  TEXT NOT NULL DEFAULT 'kkj',   -- データソース識別子 (例: 'kkj')
    source_key              TEXT NOT NULL,                  -- API側の一意キー、無ければ生成したフィンガープリント
    dedup_hash              TEXT NOT NULL,                  -- 案件名+発注機関+公告URL+公告日から生成した重複排除用ハッシュ

    -- 案件基本情報
    project_name            TEXT NOT NULL,
    organization_name       TEXT,
    organization_type       TEXT,                           -- 都道府県 / 市区町村 / 国 / 独立行政法人 / 公的機関 等
    prefecture               TEXT,
    municipality             TEXT,
    category                 TEXT,                          -- 案件カテゴリ(役務、物品等)
    procedure_type            TEXT,                          -- 入札形式(一般競争入札、公募等)

    -- 日程
    -- 注意: APIの TenderSubmissionDeadline はタグ名に反して、APIガイドの項目説明では
    -- 「入札開始日」とされている。応募締切と決めつけず、API由来の値と
    -- 仕様書で確認した実際の応募・企画提案締切を別カラムで保持する。
    published_date            TEXT,                          -- 公告日 (CftIssueDate, ISO8601)
    api_tender_date           TEXT,                          -- API由来 (TenderSubmissionDeadline) の生値
    application_deadline      TEXT,                          -- 仕様書等で確認した実際の応募締切
    deadline_verified         INTEGER NOT NULL DEFAULT 0,    -- application_deadlineを人/クライアントが確認済みか
    deadline_source           TEXT,                          -- 確認元(例: 仕様書p.3, 公募要項)
    opening_date               TEXT,                          -- 開札日 (OpeningTendersEvent)
    period_end_time             TEXT,                          -- 納入期限日 (PeriodEndTime)

    -- 金額
    budget_text                TEXT,
    budget_min                 INTEGER,
    budget_max                 INTEGER,

    -- 本文・リンク
    external_url               TEXT,
    description                 TEXT,
    location                     TEXT,                        -- 履行場所・納入場所
    certification                 TEXT,                        -- 参加資格(A/B/C/D等)
    attachment_urls              TEXT,                        -- JSON配列文字列
    attachment_names              TEXT,                        -- JSON配列文字列

    -- 添付資料のローカル取得・本文抽出(pypdfによるローカル処理。LLM API不使用)
    spec_text_status               TEXT NOT NULL DEFAULT 'pending',  -- pending/extracted/empty/failed/no_attachment
    spec_text_chars                 INTEGER NOT NULL DEFAULT 0,
    spec_text_pages                  INTEGER NOT NULL DEFAULT 0,
    spec_text_extracted_at            TEXT,
    spec_text_note                     TEXT,                        -- 失敗理由や画像PDFである旨
    scored_with_spec_text               INTEGER NOT NULL DEFAULT 0,  -- 抽出本文を含めて再スコアリング済みか

    -- ルールベース判定フラグ (キーワードグループ一致)
    video_match                   INTEGER NOT NULL DEFAULT 0,   -- GROUP A 映像・動画
    documentary_match              INTEGER NOT NULL DEFAULT 0,   -- GROUP B ドキュメンタリー
    social_issue_match              INTEGER NOT NULL DEFAULT 0,   -- GROUP C 社会課題
    local_industry_match             INTEGER NOT NULL DEFAULT 0,   -- GROUP D 地域産業
    youth_match                       INTEGER NOT NULL DEFAULT 0,   -- GROUP E 若者
    community_match                    INTEGER NOT NULL DEFAULT 0,   -- GROUP F 地域・コミュニティ
    education_match                     INTEGER NOT NULL DEFAULT 0,   -- 教育・探究

    -- 主人公性フラグ(一次判定。最終判断はMCPクライアント側)
    human_story_candidate                 INTEGER NOT NULL DEFAULT 0,
    project_story_candidate                INTEGER NOT NULL DEFAULT 0,

    -- スコア
    keyword_score                            INTEGER NOT NULL DEFAULT 0,   -- 0-100

    -- ステータス管理
    status                                     TEXT NOT NULL DEFAULT 'new',  -- new/reviewing/candidate/proposal/applied/won/lost/ignored/expired
    user_priority                               INTEGER,
    memo                                         TEXT,

    created_at                                   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                                    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_dedup_hash ON opportunities(dedup_hash);
CREATE INDEX IF NOT EXISTS idx_opportunities_source_key ON opportunities(source, source_key);
CREATE INDEX IF NOT EXISTS idx_opportunities_prefecture ON opportunities(prefecture);
CREATE INDEX IF NOT EXISTS idx_opportunities_published_date ON opportunities(published_date);
CREATE INDEX IF NOT EXISTS idx_opportunities_api_tender_date ON opportunities(api_tender_date);
CREATE INDEX IF NOT EXISTS idx_opportunities_application_deadline ON opportunities(application_deadline);
CREATE INDEX IF NOT EXISTS idx_opportunities_spec_text_status ON opportunities(spec_text_status);
CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_keyword_score ON opportunities(keyword_score);

-- 収集処理ログ (要件33)
CREATE TABLE IF NOT EXISTS collection_logs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source            TEXT NOT NULL,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    fetched_count     INTEGER NOT NULL DEFAULT 0,
    new_count         INTEGER NOT NULL DEFAULT 0,
    duplicate_count   INTEGER NOT NULL DEFAULT 0,
    error_count       INTEGER NOT NULL DEFAULT 0,
    duration_seconds  REAL,
    note              TEXT
);
