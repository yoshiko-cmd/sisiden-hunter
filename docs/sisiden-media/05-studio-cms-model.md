# STEP 5. STUDIO CMS モデル設計

## 5-1. 2つの構成方式

| | 方式A: STUDIO CMS ネイティブ | 方式B: 外部データ + Data Connect API |
|---|---|---|
| 正本 | STUDIO CMS | 外部（本リポジトリ `content/` / microCMS / 自社API） |
| 必要プラン | Personal以上（Businessが望ましい） | **Business以上（必須）** |
| アイテム上限 | Business 5,000 / Business Plus 15,000 | 実質無制限（外部側の制限に従う） |
| 編集体験 | ◎ STUDIO編集画面で完結 | △ 外部CMSまたはファイル編集 |
| リレーション | ○ 参照プロパティ（片方向） | ◎ 外部側で自由に設計 |
| エクスポート | **× 不可（重大なロックイン）** | ◎ 正本が外にある |
| 構造化データ | ○ CMSプロパティを差し込める | ○ 取得データをJSON-LDに使える |
| 推奨フェーズ | **Phase 1〜3（〜300本）** | Phase 4以降 / 1,000本規模 |

### 結論: 方式Aで開始し、正本のミラーを外に持つ

```
STUDIO CMS（編集・表示）  ←─ 手入力 ─  編集部
        │
        │ 月1回エクスポート（手動 or スクリプト）
        ▼
本リポジトリ content/*.yaml（正本ミラー・Git管理）
        │
        ├→ 将来: Data Connect API として配信（方式Bへ移行）
        ├→ 将来: sisiden.jp への移行データ
        └→ 今すぐ: JSON-LD生成 / 整合性チェック / グラフ可視化
```

STUDIO CMSにエクスポート機能がない以上、**一次情報をSTUDIOだけに置くのは資産管理として危険**。
[付録C](./integration-toolkit.md) のツールキットがこのミラーを担う。

---

## 5-2. プロパティ型の凡例

| 記号 | STUDIOのプロパティ型 |
|---|---|
| `T` | テキスト（1行） |
| `TA` | テキスト（複数行） |
| `RT` | リッチテキスト |
| `IMG` | 画像 |
| `DATE` | 日付 |
| `SEL` | セレクト（単一選択） |
| `MSEL` | マルチセレクト（複数選択） |
| `REF1` | 参照（シングル / 他モデル1件） |
| `REFn` | 参照（マルチ / 他モデル複数件） |
| `SLUG` | スラッグ |
| `SEO` | STUDIO標準のSEO設定欄（各アイテムに標準装備） |

**【要確認】** 数値型・真偽値型の有無はプラン/バージョンにより異なる場合がある。
本設計では使用を避け、必要箇所は `SEL` または `T` で代替している。

---

## 5-3. モデル1: DOCUMENTARIES（ドキュメンタリー）★最重要

| # | プロパティ名 | ラベル | 型 | 必須 | 説明・入力例 |
|---|---|---|---|---|---|
| 1 | `slug` | スラッグ | SLUG | ● | `tonkan` |
| 2 | `title` | 作品タイトル | T | ● | `TONKAN` |
| 3 | `subtitle` | サブタイトル | T | ● | `若者がつくった、街の居場所。` |
| 4 | `title_en` | 英語タイトル | T | | `TONKAN` |
| 5 | `key_visual` | キービジュアル | IMG | ● | 16:9 / 2400×1350px以上 |
| 6 | `portrait_visual` | 縦位置ビジュアル | IMG | | 3:4。一覧のバリエーション用 |
| 7 | `youtube_id` | YouTube動画ID | T | ● | `dQw4w9WgXcQ`（URLではなくIDのみ） |
| 8 | `duration` | 上映時間 | T | ● | `11:24`（`M:SS` 形式・VideoObject用） |
| 9 | `published_at` | 公開日 | DATE | ● | 映像のYouTube公開日 |
| 10 | `updated_at` | 更新日 | DATE | | ページ内容の最終更新日 |
| 11 | `lead` | リード文 | TA | ● | 120〜160字。**冒頭に結論**（AIO） |
| 12 | `introduction` | この物語について | RT | ● | 400〜800字 |
| 13 | `story` | あらすじ | RT | ● | 600〜1,200字。ネタバレの範囲は編集判断 |
| 14 | `background` | この物語の背景 | RT | ● | 社会的・地域的背景 |
| 15 | `after_story_summary` | その後（要約） | RT | | 詳細は AFTER STORY 記事へ |
| 16 | `people` | 登場人物 | REFn → PEOPLE | ● | 主人公を先頭に |
| 17 | `issues` | 社会課題 | REFn → ISSUES | ● | 1〜3個 |
| 18 | `areas` | 地域 | REFn → AREAS | ● | |
| 19 | `organizations` | 企業・団体 | REFn → ORGANIZATIONS | | 取材先・協力 |
| 20 | `tags` | タグ | REFn → TAGS | | 最大5個 |
| 21 | `related_articles` | 関連記事 | REFn → ARTICLES | | **逆参照の代替**（[STEP 2-5](./02-information-architecture.md)） |
| 22 | `related_documentaries` | 次に見る作品 | REFn → DOCUMENTARIES | | 自己参照。2〜3件 |
| 23 | `credit_direction` | 監督 | T | ● | |
| 24 | `credit_production` | 制作 | T | ● | `SISIDEN / 株式会社シシクリエイション` |
| 25 | `credit_cinematography` | 撮影 | T | | |
| 26 | `credit_editing` | 編集 | T | | |
| 27 | `credit_others` | その他クレジット | TA | | 音楽・ナレーション等 |
| 28 | `shoot_period` | 取材・撮影期間 | T | ● | `2025年6月〜2025年9月`（**E-E-A-T**） |
| 29 | `shoot_location` | 取材地 | T | ● | `神奈川県横浜市`（**E-E-A-T**） |
| 30 | `client` | 制作形態 | SEL | ● | `SISIDENオリジナル` / `企業協働` / `自治体協働` |
| 31 | `status` | 公開状態 | SEL | ● | `公開` / `準備中` / `非公開` |
| 32 | `is_featured` | トップ掲載 | SEL | | `FEATURED` / `-`。**1件だけ**FEATUREDにする |
| 33 | `order` | 並び順 | T | | `010` `020`（3桁ゼロ埋め。手動並べ替え用） |
| 34 | SEO設定 | | SEO | ● | SEOタイトル / メタディスクリプション / OGP画像 |

### `client`（制作形態）を必ず出す理由

企業協働作品を「制作実績」に見せないために、**逆に明示する**。
ページ下部に「この作品は○○との協働制作です」と書くことは、隠すよりも編集的誠実さを示す。
広告・PR表記の透明性は E-E-A-T の評価対象であり、AI検索も出所を重視する。

---

## 5-4. モデル2: ARTICLES（ストーリー）

| # | プロパティ名 | ラベル | 型 | 必須 | 説明・入力例 |
|---|---|---|---|---|---|
| 1 | `slug` | スラッグ | SLUG | ● | `tonkan-interview-ogura` |
| 2 | `title` | タイトル | T | ● | 30〜45字 |
| 3 | `lead` | リード文 | TA | ● | **120〜160字。冒頭1文で問いに答える**（AIO最重要） |
| 4 | `eyebrow` | 前置き見出し | T | | `TONKAN ─ 証言 01` |
| 5 | `hero_image` | メイン写真 | IMG | ● | 16:9 |
| 6 | `hero_caption` | 写真キャプション | T | | 撮影場所・日時を含める |
| 7 | `body` | 本文 | RT | ● | [記事内ブロック仕様](#5-4-1-本文リッチテキストの構成要素)参照 |
| 8 | `category` | カテゴリ | REF1 → CATEGORIES | ● | 1記事1カテゴリ |
| 9 | `documentary` | 関連ドキュメンタリー | REF1 → DOCUMENTARIES | ● | **必須。所属作品のない記事は作らない** |
| 10 | `people` | 登場人物 | REFn → PEOPLE | | |
| 11 | `issues` | 社会課題 | REFn → ISSUES | | |
| 12 | `areas` | 地域 | REFn → AREAS | | |
| 13 | `organizations` | 企業・団体 | REFn → ORGANIZATIONS | | |
| 14 | `tags` | タグ | REFn → TAGS | | 最大5個 |
| 15 | `related_articles` | 関連記事 | REFn → ARTICLES | | 自己参照。2〜4件 |
| 16 | `published_at` | 公開日 | DATE | ● | |
| 17 | `updated_at` | 更新日 | DATE | | 実質的な加筆時のみ更新（誤字修正では更新しない） |
| 18 | `interview_date` | 取材日 | DATE | ● | **E-E-A-T / AIO最重要** |
| 19 | `interview_location` | 取材場所 | T | ● | `神奈川県横浜市 TONKAN店舗` |
| 20 | `interview_subjects` | 取材対象者 | T | ● | `小倉莉恩（TONKAN）ほか2名` |
| 21 | `author` | 取材・文 | REF1 → PEOPLE | ● | **執筆者は必ず人物ページを持つ** |
| 22 | `photographer` | 撮影 | T | | |
| 23 | `editor` | 編集 | T | | |
| 24 | `supervisor` | 監修 | REF1 → PEOPLE | | 専門家監修がある記事のみ |
| 25 | `sources` | 出典・参考資料 | RT | | 公的データ・報告書。**リンク付きで列挙** |
| 26 | `reading_time` | 読了目安 | T | | `約8分` |
| 27 | `status` | 公開状態 | SEL | ● | `公開` / `下書き` |
| 28 | `is_featured` | 注目記事 | SEL | | トップの LATEST STORIES 上部固定用 |
| 29 | SEO設定 | | SEO | ● | |

### 5-4-1. 本文リッチテキストの構成要素

STUDIOのリッチテキストで表現し、CSSで装飾する。

| ブロック | 記法 | 用途 |
|---|---|---|
| 大見出し | H2 | 記事の章。**問いの形にする**（AIO） |
| 小見出し | H3 | 章内の節 |
| 引用（証言） | blockquote | **話者の言葉。記事の主役。大きく組む** |
| 強調リード | 太字段落 | 段落冒頭の要約 |
| 写真 | 画像 | キャプション必須 |
| 解説BOX | 区切り線 + H3「解説」 | 用語・制度・背景の説明。**AI検索が抽出しやすい単位** |
| データ | 表 | 出典を直下に明記 |
| 関連リンク | リンク | 作品・人物・課題への内部リンク |

**【STUDIOの制約】** リッチテキスト内にカスタムHTML/埋め込みブロックを差し込むことは
できない。YouTube埋め込みや「解説BOX」の凝った装飾を本文の途中に置きたい場合は、

- 代替1: **本文を `body_1` / `body_2` に分割**し、その間にSTUDIOのパーツを配置する
  （記事テンプレートに「映像埋め込みセクション」を固定配置）
- 代替2: リッチテキストのスタイル（引用・見出し）をCSSで作り込み、装飾の必要性自体を減らす

→ **代替2を主とし、必要な作品だけ代替1を使う。**
記事ごとにレイアウトが変わる設計は、1,000本規模では必ず破綻する。

---

## 5-5. モデル3: PEOPLE（人物）

| # | プロパティ名 | ラベル | 型 | 必須 | 説明 |
|---|---|---|---|---|---|
| 1 | `slug` | スラッグ | SLUG | ● | `rion-ogura` |
| 2 | `name` | 氏名 | T | ● | `小倉 莉恩` |
| 3 | `name_kana` | ふりがな | T | ● | `おぐら りおん`（50音ソート用） |
| 4 | `name_en` | ローマ字表記 | T | | `Rion Ogura` |
| 5 | `role` | 役割 | SEL | ● | `主人公` / `登場人物` / `専門家` / `制作者` / `編集部` |
| 6 | `title` | 肩書き | T | ● | `大学生 / TONKAN` |
| 7 | `portrait` | ポートレート | IMG | ● | 1:1 または 3:4 |
| 8 | `lead` | 一文紹介 | TA | ● | 60〜100字。**「誰が何をしている人か」を1文で**（AIO） |
| 9 | `profile` | プロフィール | RT | ● | 経歴・活動 |
| 10 | `quote` | この人が語った言葉 | TA | | 象徴的な一言。人物ページの主役 |
| 11 | `quote_source` | 言葉の出典 | REF1 → ARTICLES | | どの記事での発言か |
| 12 | `documentaries` | 出演作品 | REFn → DOCUMENTARIES | | |
| 13 | `articles` | 関連記事 | REFn → ARTICLES | | 逆参照の代替 |
| 14 | `organizations` | 所属 | REFn → ORGANIZATIONS | | |
| 15 | `areas` | 活動地域 | REFn → AREAS | | |
| 16 | `issues` | 関わる社会課題 | REFn → ISSUES | | |
| 17 | `after_story` | その後 | RT | | 近況 |
| 18 | `url_official` | 公式サイト | T | | Person構造化データの `sameAs` に使用 |
| 19 | `url_social` | SNS | TA | | 1行1URL。`sameAs` に使用 |
| 20 | `is_editorial` | 編集部メンバー | SEL | | `YES` / `-`。executive/author 表示の制御 |
| 21 | `consent_status` | 掲載同意 | SEL | ● | `取得済` / `確認中`。**公開前チェック用** |
| 22 | `status` | 公開状態 | SEL | ● | |
| 23 | SEO設定 | | SEO | ● | |

### `consent_status`（掲載同意）を必須にする理由

人物ページは、本人の氏名・肖像・発言を**検索可能な形で恒久的に公開する**。
映像出演の同意と、人物データベース化の同意は別物である。

- `取得済` 以外のアイテムは公開しない（運用ルール）
- 削除依頼への対応手順を `/sisiden/about/reporting-policy/` に明記する

ドキュメンタリーメディアとして、これは技術要件ではなく**倫理要件**である。

---

## 5-6. モデル4: ISSUES（社会課題）★AIO最重要

| # | プロパティ名 | ラベル | 型 | 必須 | 説明 |
|---|---|---|---|---|---|
| 1 | `slug` | スラッグ | SLUG | ● | `youth-community-space` |
| 2 | `title` | 課題名 | T | ● | `若者の居場所` |
| 3 | `question` | 問い | T | ● | **`若者の居場所とは何か？`** ← H1に使う |
| 4 | `answer` | 結論・概要 | TA | ● | **200〜300字。問いへの直接の回答**。AI検索が抜くのはここ |
| 5 | `hero_image` | メイン画像 | IMG | ● | 取材写真を使う（ストック写真を使わない） |
| 6 | `background` | 背景 | RT | ● | 構造・経緯・統計 |
| 7 | `what_we_saw` | SISIDENが現場で見たこと | RT | ● | **一次情報。このセクションが競争優位の核** |
| 8 | `voices` | 当事者の声 | RT | ● | 引用形式。話者名と取材日を明記 |
| 9 | `documentaries` | 関連作品 | REFn → DOCUMENTARIES | ● | |
| 10 | `articles` | 関連記事 | REFn → ARTICLES | | |
| 11 | `people` | 関連人物 | REFn → PEOPLE | | |
| 12 | `areas` | 関連地域 | REFn → AREAS | | |
| 13 | `related_issues` | 隣接する課題 | REFn → ISSUES | | 自己参照 |
| 14 | `data_sources` | データ・出典 | RT | ● | **公的統計を出典リンク付きで**。E-E-A-T |
| 15 | `faq` | よくある問い | RT | | Q&A形式。FAQPage構造化データに使用 |
| 16 | `supervisor` | 監修 | REF1 → PEOPLE | | 専門家監修があれば強い |
| 17 | `published_at` | 公開日 | DATE | ● | |
| 18 | `updated_at` | 更新日 | DATE | ● | **ハブページは更新し続ける。更新日が新しいことが重要** |
| 19 | `status` | 公開状態 | SEL | ● | |
| 20 | SEO設定 | | SEO | ● | |

### ISSUEページの原則

- **1本作るのに最低20時間かける。** 量産しない
- `what_we_saw` が書けないテーマは、ISSUEページを作らない（取材していないから）
- 公的統計は必ず1次ソース（省庁・自治体）にリンクする。まとめサイトを参照しない
- 年1回は必ず見直し、`updated_at` を更新する

---

## 5-7. モデル5-8（AREAS / ORGANIZATIONS / CATEGORIES / TAGS）

### AREAS（地域）

| プロパティ | ラベル | 型 | 必須 |
|---|---|---|---|
| `slug` | スラッグ | SLUG | ● |
| `name` | 地域名 | T | ● |
| `name_kana` | ふりがな | T | ● |
| `prefecture` | 都道府県 | SEL | ● |
| `region_block` | 地方ブロック | SEL | ● |
| `hero_image` | メイン画像 | IMG | |
| `lead` | 一文紹介 | TA | ● |
| `description` | 地域の文脈 | RT | |
| `documentaries` | 関連作品 | REFn → DOCUMENTARIES | |
| `articles` | 関連記事 | REFn → ARTICLES | |
| `issues` | 現れている課題 | REFn → ISSUES | |
| `latitude` / `longitude` | 緯度 / 経度 | T | |
| `status` | 公開状態 | SEL | ● |
| SEO設定 | | SEO | ● |

### ORGANIZATIONS（企業・団体）

| プロパティ | ラベル | 型 | 必須 |
|---|---|---|---|
| `slug` / `name` / `name_en` | | SLUG / T / T | ● / ● / |
| `org_type` | 種別 | SEL（`企業`/`自治体`/`業界団体`/`省庁`/`NPO`/`教育機関`） | ● |
| `logo` | ロゴ | IMG | |
| `lead` | 一文紹介 | TA | ● |
| `description` | 概要 | RT | |
| `url_official` | 公式サイト | T | ● |
| `documentaries` / `articles` / `areas` | 関連 | REFn | |
| `status` | 公開状態 | SEL | ● |

### CATEGORIES（記事カテゴリ / 6件固定）

| プロパティ | ラベル | 型 | 例 |
|---|---|---|---|
| `slug` | スラッグ | SLUG | `interview` |
| `number` | 番号 | T | `01` |
| `name_en` | 英語名 | T | `INTERVIEW` |
| `name_ja` | 日本語名 | T | `証言` |
| `description` | 定義文 | TA | `主人公・登場人物へのロングインタビュー。…` |
| `order` | 並び順 | T | `010` |

### TAGS（横断タグ / noindex）

| プロパティ | ラベル | 型 |
|---|---|---|
| `slug` / `name` | | SLUG / T |
| `description` | 説明 | TA |
| `group` | 分類 | SEL（`テーマ`/`産業`/`価値`） |

---

## 5-8. モデル種別の割り当てと縮退案（残枠5）

実機確認の結果、**モデル枠の残りは5**。ただしSTUDIOのモデルには4種別があり、
**カテゴリタイプとカスタムタイプは枠を消費していない**
（[STEP 1-1B](./01-current-site-analysis.md)）。

### 割り当て

| モデル | 作る種別 | 消費枠 |
|---|---|---|
| `DOCUMENTARIES` `ARTICLES` `ISSUES` | 記事タイプ | 3 |
| `PEOPLE` | ユーザータイプ | 1 |
| `CATEGORIES` `AREAS` `ORGANIZATIONS` | カテゴリタイプ | 0 |
| `TAGS` | カスタムタイプ | 0 |
| | | **4 / 5** |

予備1枠。`AREAS` をカテゴリタイプで作れない場合は記事タイプへ格上げする（5/5）。

### 記事タイプの既定プロパティとの対応

記事タイプは、タイトル・Slug・Cover・テキスト・公開日時を最初から持つ。
本章のプロパティ表と**意味が重なるものは既定項目を流用し、二重に作らない**。

| 本章の定義 | 記事タイプの既定 |
|---|---|
| `title` | タイトル |
| `slug` | Slug |
| `key_visual`（作品）/ `hero_image`（記事） | Cover |
| `published_at` | 公開日時 |

### それでも枠が足りない場合の縮退案

カテゴリタイプが枠を消費することが判明した場合は、以下の順で削る。



| 優先度 | 縮退内容 | 節約 | 失うもの |
|---|---|---|---|
| 1 | **TAGS を ARTICLES/DOCUMENTARIES の `MSEL`（マルチセレクト）に統合** | 1枠 | タグページ。ただし元々noindex推奨なので損失は小さい |
| 2 | **CATEGORIES を `SEL`（セレクト）に統合** | 1枠 | カテゴリ別一覧ページ、カテゴリ定義文。**動的リストのフィルターでカテゴリ別表示は可能**なので、静的ページ6枚で代替できる |
| 3 | **ORGANIZATIONS を `T`（テキスト）に降格** | 1枠 | 組織ページ、Organization構造化データ。Phase 3まで不要なので影響小 |
| 4 | AREAS を `SEL` に統合 | 1枠 | 地域ハブページ。**ここから先は情報設計の根幹を壊す。推奨しない** |

→ 1〜3で3枠節約でき、**最小5モデル**（DOCUMENTARIES / ARTICLES / PEOPLE / ISSUES / AREAS）で成立する。

**絶対に削ってはいけないのは DOCUMENTARIES / PEOPLE / ISSUES の3つ。**
これがSISIDENを「ブログ」ではなく「Knowledge Archive」にしている構造そのもの。

---

## 5-9. STUDIOでの「できる / できない / 代替」

| やりたいこと | STUDIO | 代替 |
|---|---|---|
| モデル間のリレーション | ○ 参照プロパティ（シングル/マルチ） | - |
| 逆参照の自動表示 | △ 専用機能なし。動的リストのフィルターで**【要確認】** | 双方向に参照を張る（[STEP 2-5](./02-information-architecture.md)） |
| 複数条件での絞り込み | ○ 2026年4月のアップデートで複合フィルター対応 | - |
| CMSアイテムの並べ替え | ○ プロパティ指定でソート | `order` プロパティ（3桁ゼロ埋め文字列）で手動制御 |
| サイト内全文検索 | × 標準機能なし | Google Programmable Search / Algolia を**カスタムコードで**埋め込む。またはタグ・カテゴリ絞り込みで代替（Phase 3） |
| CMSデータのエクスポート | **× 不可** | **本リポジトリ `content/` に正本ミラーを持つ**（[付録C](./integration-toolkit.md)） |
| CMSデータの一括インポート | △ WordPress XML からの一括インポートに対応 | 本リポジトリの `scripts/media_export.py --format wxr` がWXRを生成 |
| 外部APIからのデータ取得 | ○ **Data Connect API**（Business以上）。一覧→動的リスト、詳細→動的ページ | - |
| 記事本文の途中に自由なパーツ | × リッチテキスト内に埋め込み不可 | 本文を分割 + テンプレート固定パーツ（[5-4-1](#5-4-1-本文リッチテキストの構成要素)） |
| JSON-LD | ○ ページ設定の構造化データ欄。動的ページでCMSプロパティを差し込める | [STEP 8](./08-structured-data.md) |
| head へのカスタムコード | ○ サイト全体/ページ個別。head内でCMSプロパティ・URL変数が使える | - |
| 301リダイレクト | **【要確認】** | 非対応ならCDN/プロキシ層で処理。**そもそもパスを変更しない設計にする**（[STEP 4-5](./04-url-design.md)） |
| 下書きプレビュー共有 | ○ プレビューURL | - |
| 承認フロー（編集長承認） | × | `status` プロパティ + 運用ルールで代替 |

---

## 5-10. 入力必須チェックリスト（公開前）

編集部が公開ボタンを押す前に確認する。

### 記事

- [ ] `lead` の1文目が、記事の問いに答えているか
- [ ] `documentary`（所属作品）が設定されているか
- [ ] `interview_date` / `interview_location` / `interview_subjects` が埋まっているか
- [ ] `author` が人物ページにひも付いているか
- [ ] 登場人物すべてが `people` に設定され、`consent_status` が `取得済` か
- [ ] `issues` が1つ以上設定されているか
- [ ] SEOタイトル（32字以内）・メタディスクリプション（120字前後）・OGP画像
- [ ] 本文に内部リンクが3本以上あるか
- [ ] 統計・データを使った箇所に `sources` があるか
- [ ] 作品側の `related_articles` にこの記事を追加したか ← **忘れやすい**

### 作品

- [ ] `youtube_id` が正しいか（URLではなくIDか）
- [ ] `duration` が `M:SS` 形式か
- [ ] `shoot_period` / `shoot_location` が入っているか
- [ ] `client`（制作形態）が正しいか
- [ ] `people` の先頭が主人公か
