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

### 網羅性の限界(重要)

**官公需情報ポータルサイトは、全国すべての案件の掲載を保証していません。**
掲載は各発注機関の登録・連携状況に依存するため、以下が起こり得ます。

- ポータルに載っていない案件が存在する(特に小規模自治体、外郭団体)
- 自治体の公式サイトにのみ掲載される「公募型プロポーザル」「企画提案」「業務委託公募」がある
- APIガイド自身が `Category` / `ProcedureType` を「完全にデータが整備されておりません」と明記
- 公告文が画像PDFの場合、`ProjectDescription` に全文が入らないことがある

したがって本システムは**「網を張る道具」であって「全件を保証する台帳」ではありません**。
重要な自治体については、ポータルと併せて公式サイトの確認を推奨します。

### 複数データソースへの拡張

`opportunities.source` カラムに出所を記録しており、将来の第2ソース追加を前提とした設計です。
重複排除は `source` + `source_key` を優先し、取得できない場合のみ
案件名+発注機関+公告URL+公告日のハッシュで判定するため、ソースが増えても
同一案件の二重登録を防げます。

第2ソースとして想定しているもの:

- 自治体公式サイトの「公募型プロポーザル」「企画提案」「業務委託公募」ページ(HTML取得)
- 各自治体のRSS/新着情報フィード

追加する場合は `src/collectors/` に新しいコレクターを置き、
`collect()` と同じ形式(案件辞書のリスト)を返すようにすれば、
重複排除・スコアリング・DB保存・MCPツールはそのまま再利用できます。

### 実データ取得は未検証(正直な現状)

**このリポジトリを作成した開発環境からは、実APIへの通信ができていません。**
「できたこと」にはせず、遮断の実態をそのまま記載します。

- 遮断されているホスト: **`www.kkj.go.jp:443`** および **`kkj.go.jp:443`**
- 遮断の主体: 開発環境(サンドボックス)の組織ネットワークポリシー
- 観測された応答: プロキシのCONNECTに対し **`403 Forbidden`**
  (`gateway answered 403 to CONNECT (policy denial)`)
- 同様に `e-gov.go.jp` `chusho.meti.go.jp` `digital.go.jp` 等も遮断されており、
  官公庁ドメイン全般が対象と見られます

したがって **Phase 1の完了条件のうち「実APIから最低10件を実際に取得する」は未達成**です。
パイプライン全体の検証は、実レスポンス形式に準拠したフィクスチャ
(`tests/fixtures/kkj_sample_response.xml`、架空データ10件)で行っています。

### 実データでの検証手順(ネットワーク到達可能な環境で実行)

検証用のスクリプトを用意しています。これ1本で接続・パース・日付・添付URL・DB保存・
重複排除・スコアリングをまとめて確認できます。

```bash
python scripts/verify_live.py
```

出力例(成功時):

```
1. 実APIへの接続        [OK] 10件取得
2. XMLパース(必須項目)  [OK] source_key / project_name / organization_name / published_date
3. 日付の扱い            [OK] api_tender_dateとして保持(応募締切と同一視しない)
4. 添付URL               [OK] N/10件に添付あり
5. DB保存と重複排除      [OK] 初回10件新規 → 2回目0件新規(DB件数は10件のまま)
6. スコアリング          [OK] 最高/最低/平均スコアと上位5件を表示
```

失敗した場合は、到達できなかったホスト名とエラー内容がそのまま表示されます。
その結果を共有いただければ、原因の切り分けを行います。

## セットアップ

Python環境の準備、ライブラリ導入、DB作成、実APIへの接続確認まで自動で行います。

#### Windows

1. [リポジトリ](https://github.com/yoshiko-cmd/sisiden-hunter) の緑の **Code** ボタン →
   **Download ZIP** でダウンロード
2. ZIPを右クリック → **すべて展開**
3. 展開したフォルダの中の **`setup_windows.bat`** をダブルクリック

Pythonが入っていない場合は、その旨と導入手順が表示されます
([python.org](https://www.python.org/downloads/) からインストールし、
**インストール画面の「Add Python to PATH」に必ずチェック**を入れてください)。

#### Mac / Linux

```bash
git clone https://github.com/yoshiko-cmd/sisiden-hunter.git
cd sisiden-hunter
bash setup.sh
```

最後に「実際の案件を取得できました」と出れば成功です。失敗した場合は
到達できなかったホスト名とエラー内容が表示されるので、それを確認してください。

### 手動で設定する場合

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/init_db.py     # DBファイル(data/sisiden_opportunities.db)を作成
.venv/bin/python scripts/verify_live.py # 実APIからの取得を検証
```

## 案件収集

```bash
# 3階層で全国収集(デフォルト)
python scripts/collect.py --live

# 直近30日の公告に限定
python scripts/collect.py --live --days 30

# 階層を指定して収集(A=映像系のみ等)
python scripts/collect.py --live --tiers A,B

# 検索式を直接指定("映像 OR 動画 ANDNOT 防犯カメラ" のような式も使えます)
python scripts/collect.py --live --query ドキュメンタリー

# 47都道府県を1つずつ収集(1リクエスト1,000件の上限に達する場合)
python scripts/collect.py --live --by-prefecture

# オフライン検証(ネットワーク不要、フィクスチャデータで動作確認)
python scripts/collect.py --fixture tests/fixtures/kkj_sample_response.xml
```

### 3階層の収集クエリ

案件名に「映像」「動画」と書かれていなくても物語にできる案件を拾うため、
`config/collection_queries.yaml` で3階層の網を張ります。階層をまたいで重複排除されます。

| 階層 | 内容 | 検索方式 |
|---|---|---|
| **Priority A** | 映像、動画、映像制作、動画制作、ドキュメンタリー、密着、人物取材、記録映像 | OR検索 |
| **Priority B** | 広報、魅力発信、情報発信、PR、プロモーション、コンテンツ、ブランディング、シティプロモーション | OR検索 |
| **Priority C** | 社会課題、地域課題、地域産業、地場産業、ものづくり、職人、若者、学生、担い手、関係人口、移住、地方創生、地域活性化、まちづくり、探究学習、キャリア教育、官民連携、産学連携 | 発信・取材系の語とAND結合 |

Priority Cは単独で検索すると無関係な案件を大量に取得してしまうため、
`(社会課題 OR 地域課題 ...) AND (広報 OR 発信 OR PR OR 取材 ...)` の形で絞り込みます。
組み合わせる語は同ファイルの `modifiers` で調整できます。

1リクエストの上限は1,000件です。上限に達した場合はログに警告が出るので、
`--days` で期間を絞るか `--by-prefecture` で都道府県ごとに収集してください。

## 仕様書PDFの本文抽出(ドキュメンタリー案件の発掘)

案件名や公告文に「映像」と書かれていなくても、**仕様書の中に「ドキュメンタリー」「密着取材」と
書かれている案件**があります。これを検出するため、添付PDFをローカルに取得して
pypdfで本文を抽出し、その本文を含めて再スコアリングします。

```bash
# 未抽出かつ添付ありの案件を処理(最大50件)
python scripts/enrich.py

# スコア25点以上に限定
python scripts/enrich.py --min-score 25

# 特定案件のみ、抽出済みでも再取得
python scripts/enrich.py --id 12 --force
```

すべてローカル処理で完結し、**LLM APIは使用しません**。処理結果は `spec_text_status` に
記録されます。

| status | 意味 |
|---|---|
| `pending` | 未処理 |
| `extracted` | 本文を抽出し、再スコアリング済み |
| `empty` | PDFにテキストが埋め込まれていない(画像スキャンの可能性)。外部OCRには送りません |
| `failed` | ダウンロードまたはPDF解析に失敗(理由は `spec_text_note`) |
| `no_attachment` | 添付資料の登録なし |

**日本語PDFの抽出について**: テキスト埋め込み型のPDFからは日本語を抽出できることを
テストで検証済みです。ただし行政の公告には画像スキャンのみのPDFも存在し、その場合は
テキストが取れません。取れなかったことを `empty` として正直に記録し、
勝手にOCRや外部サービスへ送信することはしません。

## 日付の扱い(重要)

APIの `TenderSubmissionDeadline` は**タグ名に反して、APIガイドの項目説明では「入札開始日」**
とされています。応募締切と決めつけると危険なため、カラムを分けています。

| カラム | 内容 |
|---|---|
| `api_tender_date` | API由来の生値(`TenderSubmissionDeadline`)。応募締切とは限らない |
| `application_deadline` | 仕様書等で確認した**実際の応募・企画提案締切** |
| `deadline_verified` | 確認済みフラグ(`application_deadline` を設定すると1になる) |
| `deadline_source` | 確認元(例: 「仕様書 p.3 企画提案書提出期限」) |

締切での検索・並び替えは `COALESCE(application_deadline, api_tender_date)` で評価するため、
確認済みの案件は正しい締切で、未確認の案件はAPI由来の日付で扱われます。
確認した締切は `update_opportunity_status` で記録してください。

## 定期実行(cron等)

アプリ本体にスケジューラ依存のコードは入れていません。実行環境に応じて
`deploy/` の設定例を使ってください。

- `deploy/crontab.example` — cron(Linux/macOS)
- `deploy/com.sisiden.hunter.collect.plist.example` — launchd(macOS)

`scripts/collect.py` は定期実行向けに以下を備えています。

- 終了コード: `0`=正常 / `1`=エラーあり / `2`=多重起動を検知して中断
- `--log-file` でログをファイルへ出力
- `--lock-file` で多重起動を防止(前回実行が終わっていない場合は中断)

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

デフォルトはSTDIOトランスポートです。特定のMCPクライアントに依存しない設計にしています。

### クライアント別の対応状況

| クライアント | 接続方式 | 現状 |
|---|---|---|
| Claude Code | ローカルSTDIO | **そのまま使えます** |
| Claude Desktop | ローカルSTDIO | **そのまま使えます** |
| Codex CLI | ローカルSTDIO | **そのまま使えます** |
| その他STDIO対応クライアント | ローカルSTDIO | **そのまま使えます** |
| ChatGPT(Web/デスクトップ) | リモートMCP(HTTP)が必要 | **そのままでは繋がりません**(下記参照) |

**ローカルSTDIO対応クライアント**は、このリポジトリをローカルに置き、設定ファイルに
以下を追加するだけで利用できます。DBもPDFもローカルにあるため、外部公開は不要です。

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

**ChatGPT Web等のリモートMCPが必要な環境**は、ブラウザ上で動くため、手元のPCの
STDIOプロセスに直接接続できません。利用するには以下が別途必要です(Phase 1ではスコープ外)。

1. `src/mcp/server.py` の `mcp.run(transport="streamable-http")` へ切り替え(コードは対応済み)
2. インターネットから到達可能なHTTPSエンドポイントの用意(サーバー or トンネリング)
3. 認証の実装(案件データと営業判断が入るDBのため、無認証公開は不可)

現時点ではローカルSTDIOでの利用を推奨します。ChatGPTで使いたい場合は、
案件データをテキストで貼り付けて相談する運用でも同等の判断が可能です。

## MCPツール一覧

| ツール | 説明 |
|---|---|
| `search_opportunities` | 都道府県・月・スコア下限・キーワード・映像/ドキュメンタリー限定・締切確認済みか・ステータス等で案件を検索 |
| `get_opportunity` | 案件IDを指定して詳細情報を取得 |
| `get_specification` | 案件IDを指定し、添付の仕様書・公募要項PDFをダウンロード |
| `get_specification_text` | 仕様書PDFの**本文テキスト**をページ範囲指定で取得。全文を一度に返さず読み進められる |
| `update_opportunity_status` | ステータス・メモ・優先度・**確認した応募締切**をユーザー判断として保存 |
| `list_top_opportunities` | ドキュメンタリー明記 > スコア > 締切までの日数 > 新着順でランキング表示 |

### 使い方の例(自然言語)

- 「今月全国で映像案件出して」→ `search_opportunities(video_only=true, month="2026-09")`
- 「ドキュメンタリー案件だけ」→ `search_opportunities(documentary_only=true)`
- 「若者×地域産業で探して」→ `search_opportunities(keywords=["若者", "地域産業"])`
- 「3番を候補に」→ `update_opportunity_status(id=3, status="candidate")`
- 「この案件の仕様書を見せて」→ `get_specification(id=...)`
- **「仕様書を読んでSISIDEN向きか判断して」** → `get_specification_text(id=...)` を
  ページ範囲を変えながら呼び、本文を読んだ上でクライアント側が判断
- 「この案件の本当の応募締切を確認して記録して」→ `get_specification_text` で締切を読み取り、
  `update_opportunity_status(id=..., application_deadline="2026-10-03", deadline_source="仕様書p.3")`

## スコアリングロジック(ルールベース、AI不使用)

### 二段階方式を採用した理由(実データでの検証結果)

実データ890件で検証したところ、**公告文の全文に対する単純なキーワード一致では
建設工事案件が軒並み95〜100点**になりました。原因は3つです。

| 原因 | 実例 |
|---|---|
| 「密着」は建設・林業の専門用語 | 鍋山国有林森林整備事業(誘導伐:**密着**造林型) |
| 「撮影」「編集」は工事仕様書の定番 | 工事写真**撮影**、書類の**編集** |
| 官公需の公告文の定型文 | 「**中小企業**者の受注機会確保」「**環境**への配慮」「**災害**防止」 |

そこで二段階方式にしました。

**第1段階(anchor): 映像制作案件である裏付けを判定**

- `strong`: 単独で映像案件と判断できる語(映像制作、ドキュメンタリー、密着取材 等)。
  定型文には出ないため、案件名・公告文・仕様書のどこにあっても有効
- `title_only`: 案件名にあるときだけ有効な語(映像、動画、撮影、編集 等)。
  公告文では定型文に紛れるため

**第2段階(groups): 裏付けのある案件にのみテーマ加点**

映像・動画(+25) / ドキュメンタリー(+30) / 社会課題・地域産業・若者・地域・教育(各+10)、
最大100点。

裏付けが無い案件は、**案件名に**テーマ語がある場合のみ上限30点で拾います
(要件39「案件名に映像と書いていなくても物語にできる案件は重要」への配慮)。
公告文の定型文にしかテーマ語が無い案件は0点です。

### 検証結果

| 案件名 | 修正前 | 修正後 |
|---|---|---|
| 防災備蓄倉庫新築工事 | 100 | **0** |
| 鍋山国有林森林整備事業(誘導伐:密着造林型) | 95 | **0** |
| 配水管更新工事 | 50 | **0** |
| 伝統工芸職人のドキュメンタリー動画制作業務 | 75 | **75** |
| 若者の地域定着促進に関する関係人口創出事業(映像の裏付け無し) | — | **20** |

式典撮影・議会中継・防犯カメラ等は減点(`deprioritize`)します。減点判定は
**案件名のみ**を対象とし、本文で工事写真に触れているだけの本物の映像案件を
巻き添えにしません。また減点対象は `documentary_match` を落とすため、
ランキング上位に式典記録が紛れ込みません。

### キーワードを調整したら

`config/keywords.yaml` を編集したあとは、再収集せずに採点し直せます。

```bash
python scripts/rescore.py            # 全件を現在の設定で採点し直す
python scripts/rescore.py --dry-run  # 変更内容だけ確認する
```

`human_story_candidate` / `project_story_candidate` は一次判定フラグであり、最終判断は
MCPクライアント側(人間+LLMの対話)で行うことを前提としています。

キーワードは `config/keywords.yaml` を編集するだけで追加・調整できます(コード変更不要)。

## ディレクトリ構成

```
sisiden-hunter/
  README.md
  requirements.txt              本番の依存
  requirements-dev.txt           テスト専用の依存(reportlab)
  src/
    collectors/kkj.py            官公需情報ポータルAPI コレクター(3階層収集)
    database/schema.sql           DBスキーマ
    database/db.py                DB保存・検索・重複排除・ステータス更新
    scoring/keywords.py            keywords.yaml ローダー
    scoring/scorer.py              ルールベーススコアリング(仕様書本文も対象)
    attachments/downloader.py      添付PDFダウンロード(サニタイズ・サイズ制限・エラー処理)
    attachments/extractor.py       pypdfによる本文抽出(LLM API不使用)
    attachments/enrich.py          抽出+再スコアリングのパイプライン
    mcp/server.py                   MCP Server本体(6ツール)
    mcp/tools.py                     MCPツールのビジネスロジック
  data/
    sisiden_opportunities.db        SQLite DB(init_db.pyで生成、gitignore対象)
    attachments/opportunity_N/       ダウンロードした添付資料
    attachments/opportunity_N/extracted/documents.json  抽出テキスト
  tests/
    fixtures/kkj_sample_response.xml   テスト用フィクスチャ(架空データ10件)
    fixtures/kkj_error_response.xml     エラー応答のフィクスチャ
    test_pipeline.py                     自動テスト(18件)
  scripts/
    init_db.py     DB初期化
    collect.py      案件収集(cron対応: 終了コード/ログ/多重起動防止)
    enrich.py        仕様書PDFの取得・抽出・再スコアリング
  config/
    keywords.yaml           キーワード定義(スコア設定含む)
    kkj_api.yaml             官公需情報ポータルAPI接続設定
    collection_queries.yaml   3階層の収集クエリ定義
  deploy/
    crontab.example                          cron設定例
    com.sisiden.hunter.collect.plist.example  launchd設定例(macOS)
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
- [x] 3階層(映像/広報/テーマ)で収集し、階層をまたいで重複排除する
- [x] 仕様書PDFの本文を抽出し、記載されたドキュメンタリー等を検出して再スコアリングする
- [x] API由来の日付を応募締切と同一視せず、確認済み締切を別カラムで保持する
- [x] 定期実行可能な構造(スケジューラ依存コードは `deploy/` に分離)
- [x] **実APIからの取得を確認済み**(2026-09-21、Windows環境で `verify_live.py` が全項目合格。
      その後 `--days 30` の収集で890件を取得)。なお開発用のサンドボックス環境からは
      `www.kkj.go.jp:443` が組織ポリシーにより403で遮断されているため、実通信の確認は
      利用者のPCで行っています
- [x] 実データでのスコアリング精度を検証し、建設工事の誤検出を修正済み

## Phase 2/3(未実装、設計のみ意識)

- PPTX生成(`create_slide_spec` / `render_pptx` / `render_slide_preview`)
- 過去実績DB(KAJIMA TREE, TONKAN等)と新規案件の関連付け
- Google Drive連携
- 管理画面(Next.js等)
