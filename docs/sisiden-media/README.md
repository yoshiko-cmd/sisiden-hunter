# SISIDEN MEDIA 設計書

ドキュメンタリーメディア「SISIDEN」を、YouTube中心の映像メディアから
**ドキュメンタリー解説メディア / Knowledge Archive** へ拡張するための設計一式。

対象プラットフォーム: **STUDIO**（sisicreation.com 配下）
最終更新: 2026-09-20

---

## 設計思想（1行）

> **ONE DOCUMENTARY → MANY STORIES → PEOPLE → ISSUES → PLACES → KNOWLEDGE**

「記事」を最上位単位にしない。**DOCUMENTARY（作品）を最上位単位**とし、
そこに記事・人物・社会課題・地域がぶら下がる。SISIDENの資産は記事本数ではなく、
**現場で得た一次情報が相互に接続されたグラフ**である。

---

## ドキュメント構成

| # | ファイル | 内容 |
|---|---|---|
| STEP 1 | [01-current-site-analysis.md](./01-current-site-analysis.md) | 現在サイトの構造分析と前提整理 |
| STEP 2 | [02-information-architecture.md](./02-information-architecture.md) | 情報アーキテクチャ（コンテンツモデル・分類体系） |
| STEP 3 | [03-sitemap.md](./03-sitemap.md) | サイトマップ |
| STEP 4 | [04-url-design.md](./04-url-design.md) | URL設計 |
| STEP 5 | [05-studio-cms-model.md](./05-studio-cms-model.md) | STUDIO CMSモデル設計（全プロパティ一覧） |
| STEP 6 | [06-wireframes.md](./06-wireframes.md) | 各ページのワイヤーフレーム |
| STEP 7 | [07-seo-aio.md](./07-seo-aio.md) | SEO / AIO（AI検索）設計 |
| STEP 8 | [08-structured-data.md](./08-structured-data.md) | 構造化データ設計（JSON-LDコード付き） |
| STEP 9 | [09-design-system.md](./09-design-system.md) | デザインシステム |
| STEP 10 | [10-studio-implementation-guide.md](./10-studio-implementation-guide.md) | STUDIO編集画面での実装手順書 |
| 付録 A | [studio-capability-matrix.md](./studio-capability-matrix.md) | STUDIOで「できる / できない / 代替」一覧 |
| 付録 B | [editorial-guideline.md](./editorial-guideline.md) | 編集ガイドライン（AIO両立の文章設計） |
| 付録 C | [integration-toolkit.md](./integration-toolkit.md) | STUDIO連携ツールキット（本リポジトリ実装） |

---

## 最初に決めるべき3つの意思決定（結論）

### 決定1. ディレクトリは `/sisiden/` を推奨（`/media/` ではない）

| 観点 | `/sisiden/` | `/media/` |
|---|---|---|
| ブランド | URL自体がブランド名。第三者メディアとして独立して見える | コーポレートの一機能に見える。「制作会社のオウンドメディア」感が出る |
| SEO | 指名検索「SISIDEN」とURL文字列が一致。被リンクのアンカーも `sisiden` に集まる | ブランドシグナルなし |
| AIO | AIが引用時に出典URLを提示する際、`/sisiden/` はブランド名がそのまま露出 | `sisicreation.com/media/` は「会社のメディアページ」と解釈されやすい |
| 拡張性 | 将来コーポレート側が別のオウンドメディアを持っても衝突しない | 2つ目のメディアで破綻する |
| **独立ドメイン化** | `sisicreation.com/sisiden/*` → `sisiden.jp/*` を**機械的に1:1リダイレクト**できる | `/media/` はパスの意味が変わるため移行設計が複雑化 |

→ **`https://sisicreation.com/sisiden/` を採用。**

将来の独立時は `/sisiden/documentary/tonkan` → `sisiden.jp/documentary/tonkan` と、
第1階層を落とすだけで全URLが移行できる。**この「落とすだけで済む形」を初期から死守する。**

### 決定2. STUDIOプロジェクトは「同一プロジェクト内に構築」を推奨

STUDIOは **1プロジェクト = 1ドメイン**。`sisicreation.com/sisiden/` を実現する方法は2つ。

| 方式 | 内容 | 判定 |
|---|---|---|
| **A. 同一プロジェクト内**（推奨） | 既存 sisicreation.com プロジェクトに `/sisiden/...` のページを追加 | ◎ 追加コストなし・即実行可能。ただしCMSモデル数/アイテム数/ページ数をコーポレートと**共有**するため棚卸しが必須 |
| B. カスタムプロキシ | Business Plusのアドオン。サブディレクトリに別サーバーのサイトをマウント | △ 公式には「別サーバーでホストしているサイト」向け。**別STUDIOプロジェクトをマウントできるかは要問い合わせ**（`/_nuxt` の衝突リスク）。追加費用あり |

→ **Aで開始。**ただし決定3のとおり、データの正本を外に置くことでBやヘッドレス移行をいつでも選べる状態にする。

### 決定3. データの正本（Source of Truth）はSTUDIOの外に置く

**これが最重要。** STUDIO CMSには**エクスポート機能がない**（2026年9月現在）。
1,000本規模の一次情報を貯めた後に「出せない」のは、Knowledge Archiveにとって致命的。

→ 本リポジトリの `content/*.yaml` を正本とし、そこから
- STUDIO CMS 一括インポート用ファイル（WordPress XML / CSV）
- STUDIO **Data Connect API** 用の配信エンドポイント（Businessプラン以上）
- JSON-LD

を生成する。詳細は [付録C](./integration-toolkit.md)。

運用初期（〜100本）はSTUDIO CMS編集画面で直接書いてよい。
**ただしプロパティ定義だけは本設計書に合わせる**こと。合っていれば、後から正本を外に移せる。

---

## 全体像

```
                         ┌──────────────────────────┐
                         │      DOCUMENTARY         │  ← 最上位単位（作品）
                         │  本編映像 / STORY / 背景   │
                         └───────────┬──────────────┘
             ┌───────────────┬───────┴───────┬───────────────┐
             ▼               ▼               ▼               ▼
        ┌─────────┐    ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ ARTICLE │    │  PEOPLE  │   │  ISSUE   │   │   AREA   │
        │ 6カテゴリ │    │  人物    │   │ 社会課題  │   │   地域    │
        └────┬────┘    └────┬─────┘   └────┬─────┘   └────┬─────┘
             └──────────────┴──────┬───────┴──────────────┘
                                   ▼
                        別のDOCUMENTARYへ回遊
```

読者は「記事を読んで終わり」にならず、
**記事 → 人物 → 作品 → 社会課題 → 別の作品** と回遊する。
この回遊構造そのものがSISIDENの競争優位であり、AI検索が参照しやすい構造でもある。

---

## やらないこと（明文化）

- キーワード起点の量産SEO記事
- 取材していないテーマの解説記事
- 出典のない「まとめ」
- 制作実績一覧としての見せ方（企業ロゴの羅列、「制作事例」というラベル）
- 記事数をKPIにすること

SISIDENのKPIは **「一次情報ノードの数」と「ノード間の接続数」**。
