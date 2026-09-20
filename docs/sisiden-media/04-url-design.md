# STEP 4. URL設計

## 4-1. 設計原則

| # | 原則 | 理由 |
|---|---|---|
| 1 | **第1階層は `/sisiden/` 固定** | 独立ドメイン化時に「第1階層を落とすだけ」で移行が完了する |
| 2 | **英小文字・ハイフン区切りのみ** | 日本語URLはAI検索での引用時にパーセントエンコードされ判読不能になる |
| 3 | **階層は最大3** | `/sisiden/documentary/tonkan` まで。4階層以上は作らない |
| 4 | **複数形のディレクトリ名** | `stories` `people` `issues` `areas`。例外は `documentary`（後述） |
| 5 | **ナビラベルとURLを一致** | `STORIES` → `/stories/`。ユーザーの位置把握とAIのサイト構造理解の両方に効く |
| 6 | **日付をURLに入れない** | `/2026/09/...` は記事を古く見せる。SISIDENの記事は数年後も有効な一次情報である |
| 7 | **カテゴリをURLに入れない** | `/stories/interview/tonkan-ogura` にすると、カテゴリ変更でURLが変わる |
| 8 | **公開後のパス変更を禁止** | STUDIOはパス変更時に自動リダイレクトを張らない（後述） |

## 4-2. 確定URL一覧

| ページ | URL | モデル |
|---|---|---|
| トップ | `/sisiden/` | - |
| 作品一覧 | `/sisiden/documentary/` | - |
| **作品詳細** | `/sisiden/documentary/:slug` | DOCUMENTARIES |
| 記事一覧 | `/sisiden/stories/` | - |
| **記事詳細** | `/sisiden/stories/:slug` | ARTICLES |
| カテゴリ別 | `/sisiden/category/:slug` | CATEGORIES |
| 人物一覧 | `/sisiden/people/` | - |
| **人物詳細** | `/sisiden/people/:slug` | PEOPLE |
| 課題一覧 | `/sisiden/issues/` | - |
| **課題ハブ** | `/sisiden/issues/:slug` | ISSUES |
| 地域一覧 | `/sisiden/areas/` | - |
| **地域ハブ** | `/sisiden/areas/:slug` | AREAS |
| 組織一覧 | `/sisiden/organizations/` | - |
| 組織詳細 | `/sisiden/organizations/:slug` | ORGANIZATIONS |
| タグ別 | `/sisiden/tags/:slug` | TAGS（noindex） |
| About | `/sisiden/about/` | - |
| 編集方針 | `/sisiden/about/editorial-policy/` | - |
| 取材ポリシー | `/sisiden/about/reporting-policy/` | - |
| 編集部 | `/sisiden/about/team/` | - |
| プロデューサー | `/sisiden/producer/` | - |
| お問い合わせ | `/sisiden/contact/` | - |

## 4-3. 要件からの変更点と理由

| 要件の案 | 採用案 | 理由 |
|---|---|---|
| `/sisiden/articles/` | **`/sisiden/stories/`** | ナビゲーション `STORIES` と一致させる。また「記事」ではなく「物語」を扱うというメディアの主張がURLに出る |
| `/sisiden/topics/` | **`/sisiden/issues/`** | ナビ `ISSUES` と一致。`topics` は「話題」であり、SISIDENが扱うのは「課題・構造」。AI検索に対してもページの性質が明確になる |
| `/sisiden/documentary/` | **維持（単数形）** | 例外。`documentaries` は長く、英語話者にも `documentary/tonkan` のほうが「TONKANというドキュメンタリー」と読める。ナビは `DOCUMENTARIES`（複数）でよい |

## 4-4. スラッグ命名規則

### DOCUMENTARIES

```
作品の固有名を最優先。なければ「主題-地域」。

○ tonkan
○ hachijojima-typhoon
○ bandai-relocation
× documentary-001
× tonkan-wakamono-ga-tsukutta-machi-no-ibasho   （長すぎ）
```

### ARTICLES

```
{作品slug}-{カテゴリ略号}-{識別子}

○ tonkan-interview-ogura       TONKAN／証言／小倉
○ tonkan-note-01               TONKAN／取材ノート／1本目
○ tonkan-issue-youth-place     TONKAN／社会の構造／若者の居場所
○ tonkan-after-01              TONKAN／その後
```

作品slugを先頭に置くことで、
- URLを見るだけで所属作品がわかる
- 管理画面のslug昇順ソートで作品ごとにまとまる
- AI検索が記事群の関連性を推測しやすい

カテゴリ略号: `interview` / `note` / `issue` / `local` / `insight` / `after`

### PEOPLE

```
{名}-{姓} のローマ字（ヘボン式・小文字・ハイフン）

○ rion-ogura
× ogura-rion      ← 英語圏の語順に合わせる。Person構造化データのgivenName/familyNameとも整合
× rion_ogura
```

**同姓同名が出た場合**: `rion-ogura-2` ではなく `rion-ogura-tonkan` のように文脈を足す。

### ISSUES

```
問いの主語を英語で。名詞句。

○ youth-community-space        若者の居場所
○ construction-labor-shortage  建設業の担い手不足
○ steel-recycling              鉄リサイクル
○ disaster-recovery            災害復旧
○ regional-revitalization      地域創生
```

### AREAS

```
地名のローマ字。都道府県は不要（重複時のみ付ける）。

○ yokohama / hachijojima / iizuka / tsushima / hokkaido / bandai
```

### ORGANIZATIONS

```
組織名のローマ字または正式英語名。

○ kajima / fsa / tonkan / tetsu-recycle
```

## 4-5. STUDIO実装上の注意（重要）

### ① 動的ページのパスは `/sisiden/documentary/:slug` と設定する

STUDIOの動的ページは `パス + :slug` で構成される。
`/sisiden/documentary/:slug` のような**多階層パスが設定できるかを最初に実機確認**すること。

**【要確認】** 万一2階層（`/documentary/:slug`）までしか設定できない場合の代替:

| 代替案 | URL | 評価 |
|---|---|---|
| A. 第1階層を省略 | `/documentary/:slug` `/stories/:slug` | ○ 実用上問題なし。ただし「SISIDEN配下」という構造が崩れ、コーポレートのURL空間と混ざる。独立ドメイン移行は逆に簡単になる |
| B. slugに接頭辞 | `/documentary/:slug` で slug を `sisiden-tonkan` | × 醜い。採用しない |
| C. 別プロジェクト＋カスタムプロキシ | `/sisiden/` 配下を丸ごと別プロジェクトに | △ Business Plusアドオン必要 |

→ Aが現実的な代替。**ただしその場合も `/sisiden/` トップページは作り**、
そこをメディアの玄関として全ページからリンクする。

### ② パス変更は公開後に行わない

STUDIOでページパスを変更しても、**旧URLからの301リダイレクトは自動生成されない**。
変更 = 旧URLの404化 = 被リンクとインデックス評価の消失。

→ **公開前にパスを確定させる。**本章の表をそのまま設定する。

### ③ 自動生成パスの撲滅

STUDIOはページ作成時に `/qZyarGFP/8PXjMlic` のようなランダムパスを割り当てる。
[STEP 1](./01-current-site-analysis.md) のとおり、既にインデックスされているものがある。

**ページ作成直後に必ずパスを設定する**ことをチーム全体のルールにする。

### ④ 末尾スラッシュ

STUDIOの出力に合わせて統一する（通常は末尾スラッシュなし）。
サイト内リンク・構造化データ・サイトマップで**表記を揺らさない**。

## 4-6. 独立ドメイン移行計画（Phase 4）

### 移行の判断基準

以下を**すべて**満たしたら移行を検討する。

- [ ] 記事300本以上
- [ ] SISIDEN経由の月間セッションがコーポレート全体の50%以上
- [ ] 指名検索「SISIDEN」が月500回以上
- [ ] 編集部に専任が1名以上いる

満たさないうちは、コーポレートドメインのドメインパワーを借りるほうが有利。

### 移行手順

```
現在: sisicreation.com/sisiden/documentary/tonkan
移行: sisiden.jp/documentary/tonkan
```

1. `sisiden.jp` を取得し、**新しいSTUDIOプロジェクト**として構築
2. CMSデータを移行（※ STUDIOにエクスポート機能がないため、
   本リポジトリの `content/` を正本にしていれば無コストで移行できる。
   **これが正本を外に置く最大の理由**）
3. 旧URL → 新URL の1:1リダイレクト表を生成（第1階層を落とすだけ）
4. コーポレート側でリダイレクトを設定
   **【要確認】** STUDIOのリダイレクト機能の有無とワイルドカード対応。
   非対応の場合はカスタムプロキシまたはDNS/CDN層（Cloudflare等）で処理する
5. GSCでアドレス変更を申請、両ドメインを登録
6. 全リダイレクトの200/301を検証（本リポジトリの `scripts/media_export.py --redirects` が表を生成）

### 移行を安全にする設計上の仕込み（今やること）

1. **`/sisiden/` 配下のURLからコーポレート固有の語を排除**（済: 上記URL設計）
2. **記事内の内部リンクを相対パスで書かない**
   → CMSのリッチテキスト内リンクは `/sisiden/...` の絶対パスで統一。
   移行時に一括置換できる
3. **canonical を明示的に出力**（STEP 8）
4. **構造化データの `@id` に完全URLを使う**（移行時に一括置換）

---

## 4-7. noindex / canonical ポリシー

| ページ | index | canonical |
|---|---|---|
| 作品詳細・記事詳細・人物・課題・地域 | index | 自己参照 |
| 一覧1ページ目 | index | 自己参照 |
| 一覧2ページ目以降 | index | **自己参照**（1ページ目に集約しない。各ページ固有の記事が載るため） |
| カテゴリ別一覧 | index | 自己参照 |
| **タグ別一覧** | **noindex, follow** | - |
| 組織詳細（記事3本未満） | noindex, follow | - |
| 検索結果ページ | noindex, follow | - |

**「follow」は必ず付ける。** noindexでもリンクは辿らせる（回遊グラフを壊さないため）。
