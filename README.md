# SISIDEN 全国自治体案件ハンター (MVP)

株式会社シシクリエイションが展開する「SISIDEN」に適した全国の自治体・官公庁案件を
官公需情報ポータルサイト(中小企業庁)から収集し、ルールベースでスコアリングした上で、
MCP(Model Context Protocol)経由でChatGPT / Claude Desktop / Claude Code / Codex等の
どのMCPクライアントからでも検索・確認・選定できるようにするシステムです。

**OpenAI API等の従量課金LLM APIは一切使用していません。** 案件収集・一次判定は
キーワードマッチとルールベーススコアリングのみで行い、高度な判断(主人公性の最終判定、
提案戦略の検討)はMCPクライアント側の対話(人間+LLM)で行う設計です。

## API仕様への準拠状況

収集ロジックは[公式APIガイド V1.1](https://www.kkj.go.jp/doc/ja/api_guide.pdf)の実仕様に準拠しています。

| 項目 | 実装内容 |
|---|---|
| エンドポイント | `https://www.kkj.go.jp/api/` (ガイド2章) |
| 必須パラメータ | `Query` / `Project_Name` / `Organization_Name` / `LG_Code` のいずれか1つ以上(AND条件) |
| 取得件数 | `Count` を常に送信。**未指定時のデフォルトは10件しかない**ため必須。上限1,000件(ガイド3章) |
| 検索式 | `OR` / `AND`(省略可) / `ANDNOT` / `NOT` / `()` に対応。演算子の前後は半角空白(ガイド3.1) |
| 都道府県絞り込み | `LG_Code` を半角カンマ区切りで複数指定可能 |
| 期間パラメータ | `CFT_Issue_Date` / `Tender_Submission_Deadline` / `Opening_Tenders_Event` / `Period_End_Time`。`開始日/`・`開始日/終了日`・`開始終了日`・`/終了日` の4形式に対応(ガイド3.2) |
| レスポンス | XML。1件 = `<SearchResult>`、一意キー = `<Key>`、添付 = `<Attachments><Attachment><Name>/<Uri>`(複数対応) |
| オプション項目 | 該当情報が無い場合タグ自体が出力されないため、欠落を前提にパース(ガイド4.2) |
| タグ順序 | 出現順序が不定であることを前提に、順序非依存でパース |
| エラー応答 | `<Results><Error>...</Error></Results>` を検知して例外化(ガイド5章) |
| 都道府県コード | 01〜47をJIS X0401準拠で `config/kkj_api.yaml` に定義(ガイド6.1) |

**発注機関タイプ**: APIに専用タグが無いため、`CityName`/`PrefectureName`の有無と機関名から
都道府県 / 市区町村 / 国 / 独立行政法人等 / 公的機関を推定して保存します。

**Category / Procedure_Type で絞り込まない理由**: APIガイドはこの2つを「灰色部分」として
「完全にデータが整備されておりません」と明記しています。`Category=役務` で絞ると映像案件を
取りこぼすため、収集時には指定せず、DB側のスコアリングで絞り込む方針です。

**予定価格**: このAPIは金額項目を返しません(公告文PDFの中に記載)。`budget_*` カラムは
将来の抽出用に用意してありますが、現状は添付資料を読んだ上でMCPクライアント側が判断します。

### 実データ取得についての注意

このリポジトリを作成した開発環境(サンドボックス)は組織のネットワークポリシーにより
`kkj.go.jp` への接続がブロックされていたため、**実APIへの接続は未検証**です。
パイプライン全体(収集→重複排除→スコアリング→DB保存→MCP検索)の検証は、実レスポンス形式に
準拠した10件のフィクスチャ(`tests/fixtures/kkj_sample_response.xml`、架空データ)で行っています。

ネットワーク到達可能な環境では `python scripts/collect.py --live` でそのまま実データ収集に
切り替わります。実データで初回実行した際は、取得件数と各項目が期待どおり埋まっているかを
確認してください。

## セットアップ

```bash
cd sisiden-hunter
pip install -r requirements.txt
python scripts/init_db.py          # DBファイル(data/sisiden_opportunities.db)を作成
```

## 案件収集

```bash
# 全国収集(映像・ドキュメンタリー系キーワードで一括検索)
python scripts/collect.py --live

# 直近30日の公告に限定
python scripts/collect.py --live --days 30

# 単一キーワードで収集(検索式も使えます: "映像 OR 動画 ANDNOT 防犯カメラ" 等)
python scripts/collect.py --live --query ドキュメンタリー

# 47都道府県を1つずつ収集(1リクエスト1,000件の上限に達する場合)
python scripts/collect.py --live --by-prefecture

# オフライン検証(ネットワーク不要、フィクスチャデータで動作確認)
python scripts/collect.py --fixture tests/fixtures/kkj_sample_response.xml
```

APIは`LG_Code`未指定時に全国を対象とします。検索キーワードは `config/keywords.yaml` の
映像・ドキュメンタリーグループから自動構成され、OR検索式にまとめて送信されます
(URL長に配慮して10語ずつに分割、サーバー負荷に配慮してリクエスト間に1秒の待機)。

1リクエストの上限は1,000件です。上限に達した場合はログに警告が出るので、
`--days` で期間を絞るか `--by-prefecture` で都道府県ごとに収集してください。

実行するたびに新規案件のみDBに追加され、既存案件は重複登録されません
(`source` + `source_key`、無ければ 案件名+発注機関+公告URL+公告日 からハッシュを生成して判定)。
収集結果(取得件数/新規/重複/エラー/処理時間)は `collection_logs` テーブルとログに記録されます。

## テスト

```bash
python tests/test_pipeline.py
# または pytest がインストールされていれば
python -m pytest tests/ -v
```

収集→重複排除→スコアリング→DB保存→MCPツール呼び出しまでを一通り検証します。

## MCP Server の起動

```bash
python src/mcp/server.py
```

デフォルトはSTDIOトランスポートです。特定のMCPクライアントに依存しない設計にしており、
将来的に `mcp.run(transport="streamable-http")` へ切り替えることでHTTP経由の提供も可能です。

### Claude Desktop / Claude Code から使う場合の設定例

```json
{
  "mcpServers": {
    "sisiden-opportunity-mcp": {
      "command": "python",
      "args": ["/absolute/path/to/sisiden-hunter/src/mcp/server.py"]
    }
  }
}
```

ChatGPT/Codex等、STDIO MCPをサポートする他クライアントでも同様の設定で利用できます。

## MCPツール一覧

| ツール | 説明 |
|---|---|
| `search_opportunities` | 都道府県・月・スコア下限・キーワード・映像/ドキュメンタリー限定・ステータス等で案件を検索 |
| `get_opportunity` | 案件IDを指定して詳細情報を取得 |
| `get_specification` | 案件IDを指定し、添付の仕様書・公募要項PDFをダウンロード |
| `update_opportunity_status` | ステータス(candidate等)・メモ・優先度をユーザー判断として保存 |
| `list_top_opportunities` | ドキュメンタリー明記 > スコア > 締切までの日数 > 新着順でランキング表示 |

### 使い方の例(自然言語)

- 「今月全国で映像案件出して」→ `search_opportunities(video_only=true, month="2026-09")`
- 「ドキュメンタリー案件だけ」→ `search_opportunities(documentary_only=true)`
- 「若者×地域産業で探して」→ `search_opportunities(keywords=["若者", "地域産業"])`
- 「3番を候補に」→ `update_opportunity_status(id=3, status="candidate")`
- 「この案件の仕様書を見せて」→ `get_specification(id=...)`

## スコアリングロジック(ルールベース、AI不使用)

`config/keywords.yaml` に定義したキーワードグループ(映像・動画/ドキュメンタリー/社会課題/
地域産業/若者/地域コミュニティ/教育)ごとに一致した場合、それぞれの加点(最大100点)を行います。
ドキュメンタリー明記案件は+30点で最優先。式典撮影・議会中継・防犯カメラ等の単純業務のみと
推定される案件は減点(`deprioritize`)して優先度を下げます。

`human_story_candidate` / `project_story_candidate` は一次判定フラグであり、最終判断は
MCPクライアント側(人間+LLMの対話)で行うことを前提としています。

キーワードは `config/keywords.yaml` を編集するだけで追加・調整できます(コード変更不要)。

## ディレクトリ構成

```
sisiden-hunter/
  README.md
  requirements.txt
  src/
    collectors/kkj.py        官公需情報ポータルAPI コレクター
    database/schema.sql       DBスキーマ
    database/db.py            DB保存・検索・重複排除・ステータス更新
    scoring/keywords.py        keywords.yaml ローダー
    scoring/scorer.py          ルールベーススコアリング
    attachments/downloader.py  添付PDFダウンロード(サニタイズ・サイズ制限・エラー処理)
    mcp/server.py               MCP Server本体(5ツール)
    mcp/tools.py                 MCPツールのビジネスロジック
  data/
    sisiden_opportunities.db    SQLite DB(init_db.pyで生成、gitignore対象)
    attachments/                 ダウンロードした添付資料の保存先
  tests/
    fixtures/kkj_sample_response.xml   テスト用フィクスチャ(架空データ10件)
    test_pipeline.py                    自動テスト
  scripts/
    init_db.py    DB初期化
    collect.py     案件収集の実行スクリプト
  config/
    keywords.yaml   キーワード定義(スコア設定含む)
    kkj_api.yaml     官公需情報ポータルAPI接続設定
```

## ステータス値

`new`(未確認) → `reviewing`(確認中) → `candidate`(提案候補) → `proposal`(資料作成中) →
`applied`(応募済み) → `won`(受注) / `lost`(失注)。他に `ignored`(対象外) / `expired`(期限切れ)。

## 完成条件チェック(Phase 1)

- [x] 官公需情報ポータルAPIコレクターを実装(公式APIガイドV1.1の実仕様に準拠)
- [x] SQLiteへ保存できる
- [x] 重複登録しない(dedup_hashによるUNIQUE制約+アプリ側チェック)
- [x] キーワードスコアを計算できる
- [x] ドキュメンタリー案件を優先表示できる(`documentary_match`優先ソート)
- [x] MCP経由で案件検索・詳細取得・ステータス変更ができる
- [x] OpenAI APIを一切使用していない
- [ ] 実際のkkj.go.jpからの実データ取得は、開発環境のネットワーク制約により未検証
      (ネットワーク到達可能な環境で `--live` を実行することで確認できます)

## SISIDEN MEDIA(Webメディア設計・STUDIO連携)

YouTube中心のドキュメンタリーメディア「SISIDEN」を、記事・人物・社会課題・地域が
相互に接続されたWebメディアへ拡張するための設計一式と、STUDIO連携ツールを同梱しています。

- 設計書: [`docs/sisiden-media/`](docs/sisiden-media/README.md) (STEP1〜11 + 付録3点)
- STUDIOでの作業を始める人はここから: [CMSクイックスタート](docs/sisiden-media/11-cms-quickstart.md)
- 正本データ: [`content/`](content/README.md)
- CMSモデル定義: [`config/sisiden_media.yaml`](config/sisiden_media.yaml)

```bash
python scripts/media_validate.py                 # 必須項目・参照切れ・孤立ノード・掲載同意の検証
python scripts/media_export.py --format setup-minimal  # STUDIO CMS設定チェックシート(初日分/CSV)
python scripts/media_export.py --format jsonld   # ページごとのJSON-LD生成
python scripts/media_export.py --format wxr      # 記事の一括インポート用WordPress XML
python scripts/media_serve.py                    # STUDIO Data Connect API 向け配信サーバー
python tests/test_media.py                       # テスト19件
```

STUDIO CMSにはエクスポート機能がないため、`content/` を正本のミラーとして保持し、
そこからSTUDIOへの投入用ファイル・JSON-LD・配信APIを生成する構成にしています。

## Phase 2/3(未実装、設計のみ意識)

- PPTX生成(`create_slide_spec` / `render_pptx` / `render_slide_preview`)
- 過去実績DB(KAJIMA TREE, TONKAN等)と新規案件の関連付け
- Google Drive連携
- 管理画面(Next.js等)
