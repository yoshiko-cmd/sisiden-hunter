# SISIDEN 全国自治体案件ハンター (MVP)

株式会社シシクリエイションが展開する「SISIDEN」に適した全国の自治体・官公庁案件を
官公需情報ポータルサイト(中小企業庁)から収集し、ルールベースでスコアリングした上で、
MCP(Model Context Protocol)経由でChatGPT / Claude Desktop / Claude Code / Codex等の
どのMCPクライアントからでも検索・確認・選定できるようにするシステムです。

**OpenAI API等の従量課金LLM APIは一切使用していません。** 案件収集・一次判定は
キーワードマッチとルールベーススコアリングのみで行い、高度な判断(主人公性の最終判定、
提案戦略の検討)はMCPクライアント側の対話(人間+LLM)で行う設計です。

## 重要な既知の制約(このセッションで確認した事実)

この開発環境(サンドボックス)は組織のネットワークポリシーにより、
`kkj.go.jp` を含む一般の官公庁ドメインへのアウトバウンド接続がブロックされています
(疎通確認の結果、プロキシから `403 Forbidden` が返ることを確認済み)。

そのため本MVPでは:

- 収集ロジック(`src/collectors/kkj.py`)は公開情報から判明した実APIの仕様
  (パラメータ名: `Query` / `Project_Name` / `Organization_Name` / `LG_Code`、
  日付範囲パラメータ: `CFT_Issue_Date` / `Tender_Submission_Deadline` /
  `Opening_Tenders_Event` / `Period_End_Time`、レスポンス形式: XML)に基づいて実装済み。
- ただしエンドポイントの正確なパスとレスポンスXMLの要素名は
  [公式APIガイド](https://www.kkj.go.jp/doc/ja/api_guide.pdf) 本体にアクセスできず未確認のため、
  `config/kkj_api.yaml` に暫定値を記載し、**コードを変更せず設定ファイルのみ修正すれば
  実際の仕様に対応できる設計**にしている。
- パイプライン全体(収集→重複排除→スコアリング→DB保存→MCP検索)の動作確認は、
  実レスポンスを模した10件のテスト用フィクスチャ(`tests/fixtures/kkj_sample_response.xml`、
  架空データ)を使って行った。

ネットワーク到達可能な環境(ユーザーのPC等)では、`config/kkj_api.yaml` のURLを
実際のAPIガイドに合わせて修正した上で `python scripts/collect.py --live` を実行すれば、
そのまま実データ収集に切り替わります。

## セットアップ

```bash
cd sisiden-hunter
pip install -r requirements.txt
python scripts/init_db.py          # DBファイル(data/sisiden_opportunities.db)を作成
```

## 案件収集

```bash
# オフラインテスト(フィクスチャデータで動作確認)
python scripts/collect.py --fixture tests/fixtures/kkj_sample_response.xml

# 実API接続(ネットワーク到達可能な環境で。config/kkj_api.yamlのエンドポイント確認後に)
python scripts/collect.py --live --query 動画
```

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

- [x] 官公需情報ポータルAPIコレクターを実装(実API仕様に準拠、設定ファイルで調整可能)
- [x] SQLiteへ保存できる
- [x] 重複登録しない(dedup_hashによるUNIQUE制約+アプリ側チェック)
- [x] キーワードスコアを計算できる
- [x] ドキュメンタリー案件を優先表示できる(`documentary_match`優先ソート)
- [x] MCP経由で案件検索・詳細取得・ステータス変更ができる
- [x] OpenAI APIを一切使用していない
- [ ] 実際のkkj.go.jpからの実データ取得は、このサンドボックス環境のネットワーク制約により
      未検証(ネットワーク到達可能な環境で `--live` オプションを使うことで対応可能)

## Phase 2/3(未実装、設計のみ意識)

- PPTX生成(`create_slide_spec` / `render_pptx` / `render_slide_preview`)
- 過去実績DB(KAJIMA TREE, TONKAN等)と新規案件の関連付け
- Google Drive連携
- 管理画面(Next.js等)
