# STEP 10. STUDIO 実装手順書

STUDIOの編集画面でそのまま作業できる粒度で記載する。
上から順に実行すること。**順序を変えると手戻りが発生する。**

> UIのラベルはSTUDIOのバージョンにより多少異なる場合がある。
> 本書で `[ ]` はクリック対象、`>` は階層を示す。

---

## Phase 0. 事前確認と棚卸し（半日）

### 0-1. プラン・上限の確認

```
[プロジェクト設定] > [プラン]
```

| 確認 | 記入欄 |
|---|---|
| 現在のプラン | ____________ |
| CMSモデル 使用数 / 上限 | ____ / ____ |
| CMSアイテム 使用数 / 上限 | ____ / ____ |
| 公開ページ数 | ____ / 300 |

判定:
- **Business以上** → 全機能が使える。Data Connect APIも将来使える
- **Personal以下** → CMSアイテム1,000件上限。Phase 3までは可。**300本を超える前にアップグレード**
- **モデル残枠が8未満** → [STEP 5-8 縮退案](./05-studio-cms-model.md) を採用

### 0-2. 既存ページのパス棚卸し

```
[ページ一覧] を開き、全ページのパスを書き出す
```

- [ ] `/qZyarGFP/8PXjMlic` のような自動生成パスを特定する
- [ ] 不要なら非公開化、必要ならパスを設定し直す
  （※ 既にインデックスされているため、GSCで削除申請も併せて行う）
- [ ] `/sisiden` が未使用であることを確認

### 0-3. コンテンツの棚卸し

- [ ] YouTube公開済み全作品のリスト（タイトル / 公開日 / URL / 長さ / 登場人物 / 地域 / 企業）
- [ ] 取材済み・未公開の素材リスト（インタビュー録 / 写真 / 取材ノート）
- [ ] 登場人物リストと**掲載同意の取得状況**

---

## Phase 1. スタイル定義（1日）

**必ずページを作る前に行う。**

### 1-1. カラースタイルの登録

```
[デザイン] > [カラー] > [+ 追加]
```

[STEP 9-2](./09-design-system.md) の全トークンを登録する。

| 登録名 | 値 |
|---|---|
| `sisiden/black` | `#0A0A0A` |
| `sisiden/black-soft` | `#141414` |
| `sisiden/paper` | `#FAF9F7` |
| `sisiden/paper-alt` | `#F2F0EC` |
| `ink/primary` | `#14120F` |
| `ink/secondary` | `#5A554E` |
| `ink/tertiary` | `#8F8A82` |
| `on-black/primary` | `#FFFFFF` |
| `on-black/secondary` | `rgba(255,255,255,0.64)` |
| `on-black/tertiary` | `rgba(255,255,255,0.38)` |
| `accent` | `#B5452F` |
| `rule/paper` | `rgba(20,18,15,0.12)` |
| `rule/black` | `rgba(255,255,255,0.14)` |

### 1-2. テキストスタイルの登録

```
[デザイン] > [テキスト] > [+ 追加]
```

[STEP 9-3](./09-design-system.md) のスケールを全て登録する。
**Desktopの値で作成 → 各ブレークポイントに切り替えて上書き**する。

| スタイル名 | 書体 | Desktop | Mobile | 字間 | 行間 |
|---|---|---|---|---|---|
| `display` | 明朝 | 88 | 44 | 0.08em | 1.1 |
| `h1` | 明朝 | 56 | 32 | 0.02em | 1.35 |
| `h2` | 明朝 | 32 | 24 | 0.02em | 1.5 |
| `h3` | 明朝 | 22 | 18 | 0.02em | 1.6 |
| `lead` | ゴシック | 20 | 17 | 0.03em | 1.9 |
| `body` | ゴシック | 17 | 16 | 0.04em | 2.0 |
| `quote` | 明朝 | 28 | 20 | 0.02em | 1.8 |
| `meta` | ゴシック | 13 | 12 | 0.06em | 1.7 |
| `label` | 欧文 | 12 | 11 | 0.16em | 1.0 |

> **【要確認】** フォント一覧に Zen Old Mincho / Shippori Mincho / Noto Sans JP があるか。
> なければ [STEP 9-3](./09-design-system.md) の代替表から選ぶ。

---

## Phase 2. CMSモデルの作成（1日）

### 2-1. 作成順序

**参照される側から作る。**参照プロパティは、参照先モデルが存在しないと設定できない。

```
1. CATEGORIES   （他を参照しない）
2. TAGS         （他を参照しない）
3. AREAS
4. ORGANIZATIONS
5. PEOPLE       （AREAS / ORGANIZATIONS を参照）
6. ISSUES       （AREAS を参照）
7. DOCUMENTARIES（PEOPLE / ISSUES / AREAS / ORGANIZATIONS / TAGS を参照）
8. ARTICLES     （上記すべてを参照）

→ 最後に DOCUMENTARIES に related_articles（→ARTICLES）を追加する
   ※ 相互参照になるため、ARTICLES作成後でないと設定できない
```

### 2-2. モデル作成の操作

```
[CMS] > [+ 新規モデル]
  モデル名        : DOCUMENTARIES
  [作成]

[プロパティを追加] を繰り返す
  プロパティ名     : title
  表示ラベル      : 作品タイトル
  タイプ         : テキスト
  必須          : ON
```

[STEP 5](./05-studio-cms-model.md) の表をそのまま転記する。
**プロパティ名（英字）と表示ラベル（日本語）を分けて設定する**こと。
プロパティ名は後から変更しない前提で決める。

### 2-3. 参照プロパティの設定

```
[プロパティを追加]
  プロパティ名     : people
  表示ラベル      : 登場人物
  タイプ         : 参照
  参照先モデル     : PEOPLE
  選択形式       : マルチセレクト（複数選択可）   ← REFn の場合
                  シングルセレクト（1件のみ）     ← REF1 の場合
```

| モデル | 参照プロパティ | 参照先 | 形式 |
|---|---|---|---|
| ARTICLES | `category` | CATEGORIES | シングル |
| ARTICLES | `documentary` | DOCUMENTARIES | シングル |
| ARTICLES | `author` | PEOPLE | シングル |
| ARTICLES | `supervisor` | PEOPLE | シングル |
| ARTICLES | `people` `issues` `areas` `organizations` `tags` `related_articles` | 各 | マルチ |
| DOCUMENTARIES | `people` `issues` `areas` `organizations` `tags` `related_articles` `related_documentaries` | 各 | マルチ |
| PEOPLE | `documentaries` `articles` `organizations` `areas` `issues` | 各 | マルチ |
| PEOPLE | `quote_source` | ARTICLES | シングル |
| ISSUES | `documentaries` `articles` `people` `areas` `related_issues` | 各 | マルチ |
| ISSUES | `supervisor` | PEOPLE | シングル |

### 2-4. セレクト項目の選択肢

```
[プロパティを追加]
  タイプ : セレクト
  選択肢 : （1行ずつ入力）
```

| モデル | プロパティ | 選択肢 |
|---|---|---|
| DOCUMENTARIES | `client` | `SISIDENオリジナル` / `企業協働` / `自治体協働` |
| DOCUMENTARIES | `is_featured` | `FEATURED` / `-` |
| ARTICLES / 全モデル | `status` | `公開` / `下書き` / `非公開` |
| PEOPLE | `role` | `主人公` / `登場人物` / `専門家` / `制作者` / `編集部` |
| PEOPLE | `consent_status` | `取得済` / `確認中` |
| AREAS | `region_block` | `北海道` / `東北` / `関東` / `中部` / `近畿` / `中国` / `四国` / `九州・沖縄` |
| ORGANIZATIONS | `org_type` | `企業` / `自治体` / `業界団体` / `省庁` / `NPO` / `教育機関` |

### 2-5. 構造化データ用の追加プロパティ（忘れやすい）

[STEP 8](./08-structured-data.md) で判明した、表示用とマークアップ用を分ける必要があるもの。

| モデル | プロパティ | 型 | 入力例 | 用途 |
|---|---|---|---|---|
| DOCUMENTARIES | `duration_iso8601` | テキスト | `PT11M24S` | VideoObject |
| ARTICLES | `primary_issue` | 参照（ISSUES・シングル） | - | JSON-LDの `about` |
| DOCUMENTARIES | `primary_issue` | 参照（ISSUES・シングル） | - | 同上 |

### 2-6. 初期データの投入

CATEGORIES の6件を先に入れる。

| slug | number | name_en | name_ja | order |
|---|---|---|---|---|
| `interview` | 01 | INTERVIEW | 証言 | 010 |
| `field-note` | 02 | FIELD NOTE | 取材ノート | 020 |
| `social-issue` | 03 | SOCIAL ISSUE | 社会の構造 | 030 |
| `local-context` | 04 | LOCAL CONTEXT | 地域の文脈 | 040 |
| `insight` | 05 | INSIGHT | 洞察 | 050 |
| `after-story` | 06 | AFTER STORY | その後 | 060 |

`description`（定義文）は [STEP 2-3](./02-information-architecture.md) から転記する。

---

## Phase 3. 共通パーツの作成（1日）

### 3-1. SISIDENヘッダー

```
[ページ] > 新規ページ作成前に、まずヘッダーを作る
[+ ボックス] を最上部に配置 → [コンポーネント化]
  名前: sisiden-header
```

構成:
```
左: SISIDEN（ロゴテキスト。display書体・label字間）→ /sisiden/ へリンク
右: DOCUMENTARIES / STORIES / PEOPLE / ISSUES / ABOUT（label スタイル）
```

- 背景: 透過（HERO上）→ スクロールで `sisiden/paper` に変化
- **コーポレートのヘッダーを絶対に流用しない**
- モバイル: ハンバーガーメニュー（全画面オーバーレイ・黒背景）

### 3-2. SISIDENフッター

[STEP 2-6](./02-information-architecture.md) の構成でコンポーネント化する。
名前: `sisiden-footer`

最下部に必ず:
```
Produced by SISI CREATION →   （https://sisicreation.com/ へリンク）
© SISI CREATION Inc.
```

### 3-3. その他のコンポーネント

| 名前 | 内容 |
|---|---|
| `card-documentary` | 作品カード（ポスター型 3:4） |
| `card-article` | 記事カード（横長リスト型） |
| `chip-person` | 人物チップ（丸ポートレート） |
| `block-watch-documentary` | 「この物語を映像で見る」ブロック |
| `block-article-meta` | 「この記事について」ブロック |
| `section-heading` | セクション見出し + VIEW ALL |

**コンポーネント化しておくと、記事が増えてもデザイン変更が1箇所で済む。**

---

## Phase 4. ページの作成

### 4-1. 作成するページとパス設定

```
[ページ] > [+ 新規ページ]
  → 作成後、即座に [ページ設定] > [パス] を設定する
```

> **重要**: ページを作ったら**その場でパスを設定する**。
> 後回しにするとランダムパスのまま公開される事故が起きる（[STEP 1-1](./01-current-site-analysis.md)）。

| # | ページ名 | タイプ | パス | 紐付けモデル |
|---|---|---|---|---|
| 1 | SISIDEN TOP | 通常 | `/sisiden` | - |
| 2 | DOCUMENTARIES | 通常 | `/sisiden/documentary` | - |
| 3 | Documentary Detail | **動的** | `/sisiden/documentary/:slug` | DOCUMENTARIES |
| 4 | STORIES | 通常 | `/sisiden/stories` | - |
| 5 | Story Detail | **動的** | `/sisiden/stories/:slug` | ARTICLES |
| 6 | Category | **動的** | `/sisiden/category/:slug` | CATEGORIES |
| 7 | PEOPLE | 通常 | `/sisiden/people` | - |
| 8 | Person Detail | **動的** | `/sisiden/people/:slug` | PEOPLE |
| 9 | ISSUES | 通常 | `/sisiden/issues` | - |
| 10 | Issue Detail | **動的** | `/sisiden/issues/:slug` | ISSUES |
| 11 | AREAS | 通常 | `/sisiden/areas` | - |
| 12 | Area Detail | **動的** | `/sisiden/areas/:slug` | AREAS |
| 13 | Tag Detail | **動的** | `/sisiden/tags/:slug` | TAGS（noindex） |
| 14 | ABOUT | 通常 | `/sisiden/about` | - |
| 15 | 編集方針 | 通常 | `/sisiden/about/editorial-policy` | - |
| 16 | 取材ポリシー | 通常 | `/sisiden/about/reporting-policy` | - |

### 4-2. 動的ページの作成手順

```
[+ 新規ページ] > [動的ページ]
  CMSモデルを選択  : DOCUMENTARIES
  パス           : /sisiden/documentary/:slug
[作成]
```

> **【最初に検証すること】**
> `/sisiden/documentary/:slug` のような**3階層のパスが設定できるか**を
> ここで必ず確認する。
> できない場合は [STEP 4-5 の代替案A](./04-url-design.md)（`/documentary/:slug`）に切り替え、
> **全ページのパスを一括で見直してから先に進む**。
> ページを量産した後の変更は致命的な手戻りになる。

### 4-3. 動的ページへのCMS値の配置

```
テキスト要素を選択 > [CMSと接続] > プロパティを選択
```

[STEP 6](./06-wireframes.md) のワイヤーフレームの `{property}` 表記の箇所に、
対応するプロパティを接続する。

**YouTube埋め込み**
```
[+ 埋め込み] > YouTube
  動画URL : [CMSと接続] ではなくURL欄に直接
            https://www.youtube.com/embed/ + {{youtube_id}} を組み立てる
```
> **【要確認】** 埋め込みブロックのURLにCMSプロパティを差し込めるか。
> できない場合の代替:
> 1. CMSに `youtube_url`（完全URL）プロパティを追加し、そちらを接続する ← **推奨**
> 2. iframeをカスタムコードで埋め込む
>
> → **対策として、`youtube_id` と `youtube_url` の両方をCMSに持たせる。**
> `youtube_id` は構造化データ用、`youtube_url` は埋め込み用。

### 4-4. 関連リストの設定（逆参照）

DOCUMENTARY詳細ページに「関連記事」を出す。

```
[+ CMSリスト] > モデル: ARTICLES
[フィルター] を設定
```

| 方式 | 設定 | 判定 |
|---|---|---|
| **A（先に試す）** | フィルター条件: `documentary` = 現在のページのアイテム | **【要確認】**動けばこれが最良（記事追加時に自動反映） |
| **B（確実）** | 参照リスト `related_articles` を表示する | 必ず動く。記事公開時に作品側の `related_articles` への追加が必要 |

→ **Aを試し、動かなければBに切り替える。**
Bの場合、[STEP 5-10](./05-studio-cms-model.md) の公開前チェックリストの
「作品側の `related_articles` にこの記事を追加したか」が必須作業になる。

### 4-5. 一覧ページの動的リスト設定

```
[+ CMSリスト] > モデル: DOCUMENTARIES
  並び順    : published_at 降順
  表示件数  : 12
  ページング : ページネーション
  フィルター : status = 公開
```

**全リストに `status = 公開` のフィルターを必ず入れる。**
入れ忘れると下書きが公開サイトに出る。

---

## Phase 5. SEO設定

### 5-1. 各ページのSEO設定

```
[ページ設定] > [SEO]
  ページタイトル       : [CMSと接続] で組み立て
  メタディスクリプション : [CMSと接続]
  OGP画像            : [CMSと接続]
```

[STEP 7-3](./07-seo-aio.md) のテンプレートに従う。

| ページ | タイトルの組み立て |
|---|---|
| 作品詳細 | `{{title}}｜{{subtitle}}｜SISIDEN ドキュメンタリー` |
| 記事詳細 | `{{title}}｜{{documentary.title}}｜SISIDEN` |
| 課題ハブ | `{{question}}｜SISIDEN` |
| 人物詳細 | `{{name}}（{{title}}）｜SISIDEN` |

### 5-2. noindex の設定

```
Tag Detail ページ > [ページ設定] > [SEO] > [検索エンジンにインデックスさせない] をON
```

対象: Tag Detail / 検索結果ページ

### 5-3. 構造化データの設定

```
[ページ設定] > [構造化データマークアップ] を ON
> JSON-LD入力欄に [STEP 8](./08-structured-data.md) のコードを貼り付け
> {{ }} の箇所を [プロパティを挿入] で実際のCMS値に置き換える
```

設定するページ:

| ページ | 使うコード |
|---|---|
| 全ページ共通（サイト設定のカスタムコード） | Organization（[8-2](./08-structured-data.md)） |
| 作品詳細 | VideoObject + BreadcrumbList（8-3） |
| 記事詳細 | Article + BreadcrumbList（8-4） |
| 人物詳細 | Person + ProfilePage（8-5） |
| 課題ハブ | Article + ItemList（8-6） |
| トップ | WebSite（8-7） |

> **マルチ参照の配列展開ができない場合**は、`about` / `mentions` を
> `primary_issue` 1件のみの参照に変更する（[STEP 8-8](./08-structured-data.md)）。

### 5-4. サイト全体のカスタムコード

```
[プロジェクト設定] > [カスタムコード] > [head]
```

- Organization の JSON-LD
- Google Analytics 4
- Google Search Console 認証タグ（未登録なら登録する）

---

## Phase 6. 初期コンテンツの投入

### 6-1. 投入順序

```
1. CATEGORIES  6件（Phase 2-6 で投入済み）
2. AREAS       作品に登場する地域
3. ORGANIZATIONS
4. PEOPLE      ※ consent_status = 取得済 のみ
5. ISSUES      3件（本気で作る）
6. DOCUMENTARIES 3件
7. ARTICLES    9件
8. 最後に DOCUMENTARIES の related_articles を設定
```

### 6-2. 公開前チェック

[STEP 5-10](./05-studio-cms-model.md) のチェックリストを全アイテムに対して実施。

### 6-3. 公開直前の最終確認

- [ ] 全ページのパスが設計どおりか（ランダムパスが残っていないか）
- [ ] 全動的リストに `status = 公開` フィルターが入っているか
- [ ] ヘッダーにコーポレートのロゴが出ていないか
- [ ] フッターに `Produced by SISI CREATION` があるか
- [ ] モバイルで記事のリードが省略されていないか
- [ ] 構造化データを [リッチリザルトテスト](https://search.google.com/test/rich-results) で検証
- [ ] OGPを実際にSNSでシェアして確認
- [ ] `/sitemap.xml` にタグページが含まれていないか
- [ ] ページ表示速度（画像サイズが過大でないか）

---

## Phase 7. 公開後の運用

### 7-1. 記事公開フロー（毎回）

```
1. ARTICLES に新規アイテム作成
2. 必須プロパティをすべて入力（取材日・取材場所・取材対象者・執筆者）
3. 登場人物が PEOPLE に存在するか確認。なければ先に作成（同意確認）
4. issues / areas / organizations を接続
5. SEO設定（タイトル・ディスクリプション・OGP）
6. 構造化データの出力をプレビューで確認
7. ★ DOCUMENTARIES の related_articles にこの記事を追加  ← 忘れやすい
8. status = 公開
9. 公開後、リッチリザルトテストで検証
```

### 7-2. 月次の運用

| 頻度 | 作業 |
|---|---|
| 毎月 | GSCで固有名詞クエリの表示回数を確認 |
| 毎月 | AI検索（ChatGPT / Perplexity / Gemini）でISSUEの問いを投げ、引用されるか手動確認 |
| 毎月 | 孤立ページの検出（`scripts/media_validate.py`） |
| 毎月 | **CMSデータのバックアップ**（[付録C](./integration-toolkit.md)）← STUDIOにエクスポート機能がないため必須 |
| 四半期 | タグの棚卸し（使われていないタグの統廃合） |
| 半期 | ISSUEページの更新（`updated_at` を更新） |
| 半期 | AFTER STORY の企画（公開から半年経った作品） |

### 7-3. 拡張のタイミング

| 記事数 | やること |
|---|---|
| 30本 | Phase 2（ISSUES / カテゴリ別一覧）の実装 |
| 100本 | Phase 3（AREAS / ORGANIZATIONS / 検索）の実装 |
| 300本 | プランをBusiness Plusへ。独立ドメインの検討開始 |
| 500本 | Data Connect API への移行検討（[STEP 5-1 方式B](./05-studio-cms-model.md)） |

---

## 付録: 想定スケジュール

| 週 | 作業 |
|---|---|
| W1 | Phase 0（棚卸し）＋ Phase 1（スタイル定義） |
| W2 | Phase 2（CMSモデル作成）＋ Phase 3（共通パーツ） |
| W3 | Phase 4（トップ / 作品一覧 / 作品詳細） |
| W4 | Phase 4（記事一覧 / 記事詳細 / 人物） |
| W5 | Phase 5（SEO / 構造化データ）＋ Phase 6（コンテンツ投入） |
| W6 | 検証・修正・公開 |

Phase 1の初期公開は**6週間**を想定。
うち**W1のPhase 0を省略しないこと**。ここを飛ばすと後工程で必ず破綻する。
