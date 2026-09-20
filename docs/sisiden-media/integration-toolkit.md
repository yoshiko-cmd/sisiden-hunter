# 付録C. STUDIO連携ツールキット

本リポジトリに実装した、SISIDEN MEDIA の正本データ管理とSTUDIO連携の仕組み。

## C-1. なぜ必要か

STUDIO CMSには**エクスポート機能がない**（2026年9月時点）。
記事1,000本・人物400人の一次情報をSTUDIOだけに置くと、

- 独立ドメイン（`sisiden.jp`）へ移行するときにデータを持ち出せない
- プラットフォームを変えるときに全件手作業になる
- 構造化データのマルチ参照展開など、STUDIO側でできないことの逃げ場がない

これはKnowledge Archiveを名乗るメディアにとって致命的である。

```
                    ┌──────────────────────────┐
  編集部 ──手入力──▶ │      STUDIO CMS          │ ──▶ 公開サイト
                    │   （編集・表示の場）        │
                    └──────────┬───────────────┘
                               │ 月1回 反映（手動 or CSV突き合わせ）
                               ▼
                    ┌──────────────────────────┐
                    │  content/*.yaml（正本）    │  ← Git管理・差分が追える
                    └──────────┬───────────────┘
                               │
         ┌─────────────┬───────┴────────┬──────────────┐
         ▼             ▼                ▼              ▼
   検証・グラフ集計   JSON-LD生成    WXR一括インポート   Data Connect API
```

## C-2. ファイル構成

```
config/sisiden_media.yaml        CMSモデル定義（STEP 5 の正本）
content/                         コンテンツの正本
  categories/ tags/ areas/ organizations/
  people/ issues/ documentaries/ articles/
src/media/
  schema.py                      モデル定義のローダー
  content.py                     読み込み・検証・グラフ集計
  jsonld.py                      JSON-LD生成
  exporters/
    csv_export.py                CSV台帳 / STUDIO設定シート / リダイレクト表
    wxr.py                       WordPress XML（STUDIO一括インポート用）
  api/
    payload.py                   Data Connect API のレスポンス組み立て
    server.py                    配信サーバー（標準ライブラリのみ）
scripts/
  media_validate.py              検証・グラフ集計
  media_export.py                各種エクスポート
  media_serve.py                 配信API起動
tests/test_media.py              18件のテスト
```

追加の依存パッケージはない（PyYAMLのみ。既存の `requirements.txt` で足りる）。

## C-3. すぐ使えるコマンド

### 検証とグラフ集計

```bash
python scripts/media_validate.py
```

検査する内容:

| 検査 | 判定 |
|---|---|
| 必須プロパティの未入力 | ERROR |
| 参照先が存在しない（リンク切れ） | ERROR |
| セレクトの選択肢外の値 | ERROR |
| 日付形式の誤り | ERROR |
| slugの命名規則違反（英小文字・ハイフン） | ERROR |
| 記事に所属作品がない | ERROR |
| **掲載同意なしの人物が公開状態** | **ERROR** |
| ノードの接続数が2未満（回遊の行き止まり） | WARN |
| 1作品あたりの記事数が3本未満 | WARN |

同時に [STEP 2-7](./02-information-architecture.md) のKPIを出力する。

```
── Knowledge Graph ───────────────────
  ノード数                5
  エッジ数               32
  ノードあたり接続数      6.4   （目標 4.0以上）
  孤立ノード率           0.2   （目標 0.1未満）
  1作品あたり記事数       1.0   （目標 3.0以上）
```

### STUDIO CMS 設定チェックシート

```bash
python scripts/media_export.py --format setup
```

`data/media_export/studio_cms_setup.csv` に、STUDIOの編集画面で
プロパティを1つずつ作るためのシートが出る。

```
モデル,プロパティ名,表示ラベル,STUDIOで選ぶタイプ,参照先モデル,選択形式,必須,選択肢,設定済み
DOCUMENTARIES,people,登場人物,参照,PEOPLE,マルチセレクト,,,
ARTICLES,documentary,関連ドキュメンタリー,参照,DOCUMENTARIES,シングルセレクト,●,,
```

**[STEP 10 Phase 2](./10-studio-implementation-guide.md) の作業は、このCSVを
印刷して1行ずつ消し込めば完了する。**

### JSON-LD の生成

```bash
python scripts/media_export.py --format jsonld
```

`data/media_export/jsonld/` に、ページごとの完成済みJSON-LDが出る。

**これが [STEP 8-8](./08-structured-data.md) の「マルチ参照を配列展開できない」問題の解**。
STUDIOの構造化データ欄では `about` に複数の `@id` を並べることが難しいが、
ここで生成したJSON-LDは全件展開されている。

```json
"about": [
  {"@id": "https://sisicreation.com/sisiden/issues/youth-community-space#issue"}
],
"actor": [
  {"@id": "https://sisicreation.com/sisiden/people/rion-ogura#person"}
]
```

使い道は2つ。

1. **Phase 1〜3**: 重要ページだけ、生成結果をSTUDIOの構造化データ欄に貼り付ける
2. **Phase 4**: Data Connect API 経由で `jsonld` フィールドをそのまま差し込む（後述）

### 記事の一括インポート（WordPress XML）

```bash
python scripts/media_export.py --format wxr
```

`data/media_export/articles.wxr.xml` をSTUDIOのWordPressインポートに読み込ませる。

> **制約（重要）**
> WXRが表現できるのは タイトル / 本文 / 抜粋 / 公開日 / スラッグ / カテゴリ /
> タグ / 著者名 まで。**作品・人物・社会課題へのリレーションはWXRの語彙に存在しない**ため、
> インポート後にSTUDIO上で接続し直す必要がある。
>
> そのため本ツールは、
> - リレーションを `wp:postmeta`（`sisiden_documentary` など）に残す
> - 本文末尾に「この記事について」ブロック（取材日・取材場所・取材対象・執筆者）を埋め込む
>
> の2つを行い、**取材情報が失われないように**している。
> 既存記事の移行には有効だが、**新規記事はSTUDIO編集画面で直接書くほうが速い。**

### CSV台帳（バックアップ）

```bash
python scripts/media_export.py --format csv
```

モデルごとにCSVを出力する。マルチ参照は `|` 区切り。
1行目が日本語ラベル、2行目がプロパティ名、3行目以降がデータ。

**月1回、STUDIOの内容をこのCSVと突き合わせる**のが最低限のバックアップ運用。

### 独立ドメイン移行用リダイレクト表

```bash
python scripts/media_export.py --format redirects --new-base https://sisiden.jp
```

```csv
old_url,new_url,status
https://sisicreation.com/sisiden/documentary/tonkan,https://sisiden.jp/documentary/tonkan,301
```

[STEP 4-6](./04-url-design.md) の「第1階層を落とすだけ」という設計が、
実際に機械的な変換で済むことをテストで検証している
（`test_redirect_map_drops_only_the_first_path_segment`）。

## C-4. Data Connect API（Businessプラン以上）

### 起動

```bash
python scripts/media_serve.py --host 0.0.0.0 --port 8787
```

### エンドポイント

| 用途 | URL | STUDIO側の接続先 |
|---|---|---|
| ヘルスチェック | `GET /api/v1/health` | - |
| 一覧 | `GET /api/v1/documentaries` | **動的リスト** |
| 詳細 | `GET /api/v1/documentaries/{slug}` | **動的ページ / 動的モーダル** |

モデル名は `documentaries` `articles` `people` `issues` `areas`
`organizations` `categories` `tags`。

クエリパラメータ:

```
?limit=20&offset=0
?filters=documentary:tonkan        記事を作品で絞り込む
```

### レスポンス形状

microCMSと同じ形にしてある。STUDIOはmicroCMSを公式サポートしているため、
接続設定で迷わない。

```json
{
  "contents": [ { ... } ],
  "totalCount": 12,
  "offset": 0,
  "limit": 20
}
```

各アイテムの特徴:

```json
{
  "id": "tonkan",
  "slug": "tonkan",
  "url": "https://sisicreation.com/sisiden/documentary/tonkan",
  "title": "TONKAN",
  "areas": [ { "slug": "yokohama", "url": "...", "name": "横浜", "prefecture": "神奈川県" } ],
  "primary_issue": { "slug": "youth-community-space", "question": "若者の居場所とは何か？" },
  "jsonld": "{\"@context\":\"https://schema.org\",\"@graph\":[...]}"
}
```

| 工夫 | 効果 |
|---|---|
| **リレーションを要約オブジェクトとして埋め込む** | STUDIO側で `areas[0].name` のようにネストした値を直接バインドできる。追加のAPI呼び出しが不要 |
| **`jsonld` を文字列で同梱** | STUDIOの構造化データ欄にこのフィールドを挿すだけで、完全なJSON-LDが出力される。マルチ参照の展開問題が消える |
| `status != 公開` を既定で除外 | 下書きが公開サイトに出ない |

### 認証

```bash
export SISIDEN_API_TOKEN=<任意の長い文字列>
python scripts/media_serve.py
```

設定すると `Authorization: Bearer <token>` または `X-API-KEY` を要求する。
STUDIOのAPI連携設定でカスタムヘッダーとして登録する。
**未設定なら認証なし（ローカル検証用）。公開ホストに置くときは必ず設定する。**

### 公開ホストへの配置

STUDIOから到達できる**HTTPSの公開エンドポイント**が必要。

| 方式 | 補足 |
|---|---|
| Cloud Run / Render / Fly.io 等 | `python scripts/media_serve.py --host 0.0.0.0 --port $PORT` をそのまま起動 |
| 静的JSONとして配信 | 更新頻度が低いなら、`--format jsonld` と同様に一覧/詳細JSONを書き出してCDNに置く方式でもよい（サーバー不要） |

**Phase 1〜3では不要。** 方式Bへ移行する段階（記事500本前後）で使う。

## C-5. 運用フロー

### 毎月（15分）

```bash
python scripts/media_validate.py        # リンク切れ・孤立ノード・同意漏れの検出
python scripts/media_export.py --format csv   # バックアップ台帳の更新
git add content/ && git commit -m "content: 2026-10 分を反映"
```

### 記事を追加するとき

STUDIO編集画面で書く場合も、**同じ内容を `content/articles/{slug}.yaml` に残す**。
面倒に見えるが、これをやらないと3年後にデータを持ち出せない。

記事が増えて手作業がつらくなったら、方式B（Data Connect API）へ移行して
正本を1つにする。**そのときスキーマが揃っていれば移行は数日で終わる。**

## C-6. テスト

```bash
python tests/test_media.py
# または
python -m pytest tests/test_media.py -v
```

18件。検証ルール・JSON-LD生成・API応答・WXR出力・URL設計を網羅している。
特に以下は設計そのものを検証している。

| テスト | 検証している設計判断 |
|---|---|
| `test_url_design_matches_spec` | STEP 4 のURL設計 |
| `test_jsonld_expands_multi_references` | STEP 8-8 の代替策が機能すること |
| `test_validation_blocks_publishing_people_without_consent` | STEP 5-5 の倫理要件 |
| `test_redirect_map_drops_only_the_first_path_segment` | STEP 4-6 の独立ドメイン移行設計 |
