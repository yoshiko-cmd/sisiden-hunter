# STEP 8. 構造化データ設計

## 8-1. 方針

構造化データの目的は**リッチリザルトではなく、エンティティグラフの宣言**である。

SISIDENが伝えたいのは「この記事はArticleです」ではなく、

> この記事は、**小倉莉恩という人物**についての、**TONKANという映像作品**に付随する、
> **SISIDENという組織**が**2026年8月12日に横浜で取材した**一次情報である

という関係性。これを `@id` による相互参照で表現する。

### 実装方式

| 方式 | 使いどころ |
|---|---|
| **STUDIO標準の構造化データ設定** | 第一選択。ページ設定 > 構造化データマークアップ をON → JSON-LDを貼り付け → 動的ページではCMSプロパティを差し込む |
| **カスタムコード（head）** | 標準欄で足りない場合。head内でもCMSプロパティ・URL変数が使える |

**注意**: 本書のコード内 `{{property}}` は、STUDIOの編集画面で
**プロパティ挿入UIから実際の値を差し込む箇所**を示す。文字列としてコピーしても動かない。

---

## 8-2. 全ページ共通: Organization（サイト全体のカスタムコードに1回）

サイト全体の `<head>` カスタムコードに配置する。

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "https://sisicreation.com/sisiden/#organization",
  "name": "SISIDEN",
  "alternateName": ["シシデン", "SisiDen", "SISIDEN MEDIA"],
  "url": "https://sisicreation.com/sisiden/",
  "logo": {
    "@type": "ImageObject",
    "url": "https://sisicreation.com/（SISIDENロゴのURL）",
    "width": 512,
    "height": 512
  },
  "description": "SISIDENは、企業・行政・地域・社会課題の現場を第三者視点で取材し、そこで生きる人の物語をドキュメンタリーとして記録するメディアです。",
  "foundingDate": "2024-06",
  "parentOrganization": {
    "@type": "Organization",
    "name": "株式会社シシクリエイション",
    "url": "https://sisicreation.com/"
  },
  "sameAs": [
    "https://www.youtube.com/@（チャンネルID）",
    "https://note.com/sisitsukahara",
    "https://x.com/（アカウント）"
  ]
}
```

**ポイント**

- `alternateName` に `SisiDen` を入れる。[STEP 1](./01-current-site-analysis.md) の表記揺れを
  AIに「同一実体」と伝えるための措置
- `parentOrganization` でコーポレートとの関係を宣言する。
  ナビゲーション上は独立させつつ、**運営主体の透明性は構造化データで担保する**
- `@id` を固定し、以下すべてのページから参照する

---

## 8-3. ドキュメンタリー詳細ページ

`VideoObject` + `BreadcrumbList` + 登場人物の `Person` 参照を `@graph` で1つにまとめる。

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "VideoObject",
      "@id": "https://sisicreation.com/sisiden/documentary/{{slug}}#video",
      "name": "{{title}}｜{{subtitle}}",
      "description": "{{lead}}",
      "thumbnailUrl": "{{key_visual}}",
      "uploadDate": "{{published_at}}",
      "duration": "PT11M24S",
      "embedUrl": "https://www.youtube.com/embed/{{youtube_id}}",
      "url": "https://sisicreation.com/sisiden/documentary/{{slug}}",
      "publisher": { "@id": "https://sisicreation.com/sisiden/#organization" },
      "creator": { "@id": "https://sisicreation.com/sisiden/#organization" },
      "director": { "@type": "Person", "name": "{{credit_direction}}" },
      "about": [
        { "@id": "https://sisicreation.com/sisiden/issues/{{issues.slug}}#issue" }
      ],
      "contentLocation": {
        "@type": "Place",
        "name": "{{shoot_location}}"
      },
      "inLanguage": "ja"
    },
    {
      "@type": "BreadcrumbList",
      "itemListElement": [
        { "@type": "ListItem", "position": 1, "name": "SISIDEN",
          "item": "https://sisicreation.com/sisiden/" },
        { "@type": "ListItem", "position": 2, "name": "DOCUMENTARIES",
          "item": "https://sisicreation.com/sisiden/documentary/" },
        { "@type": "ListItem", "position": 3, "name": "{{title}}" }
      ]
    }
  ]
}
```

### `duration` の注意

Schema.orgは **ISO 8601 duration 形式**（`PT11M24S`）を要求する。
CMSの `duration` は `11:24` という表示用の値なので、**そのまま差し込めない**。

| 対策 | 内容 |
|---|---|
| A（推奨） | CMSに `duration_iso8601` プロパティ（T型）を追加し、`PT11M24S` を別途入力する。表示用とマークアップ用を分ける |
| B | 構造化データから `duration` を省く（必須項目ではない） |

→ **Aを採用。**プロパティを1つ増やすだけで、VideoObjectの品質が上がる。
（[STEP 5-3](./05-studio-cms-model.md) のモデル定義に `duration_iso8601` を追加すること）

---

## 8-4. 記事ページ ★最重要

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Article",
      "@id": "https://sisicreation.com/sisiden/stories/{{slug}}#article",
      "headline": "{{title}}",
      "description": "{{lead}}",
      "image": "{{hero_image}}",
      "datePublished": "{{published_at}}",
      "dateModified": "{{updated_at}}",
      "inLanguage": "ja",
      "isAccessibleForFree": true,
      "author": {
        "@id": "https://sisicreation.com/sisiden/people/{{author.slug}}#person"
      },
      "publisher": { "@id": "https://sisicreation.com/sisiden/#organization" },
      "mainEntityOfPage": "https://sisicreation.com/sisiden/stories/{{slug}}",
      "articleSection": "{{category.name_ja}}",
      "about": [
        { "@id": "https://sisicreation.com/sisiden/issues/{{issues.slug}}#issue" }
      ],
      "mentions": [
        { "@id": "https://sisicreation.com/sisiden/people/{{people.slug}}#person" }
      ],
      "isPartOf": {
        "@id": "https://sisicreation.com/sisiden/documentary/{{documentary.slug}}#video"
      },
      "video": {
        "@id": "https://sisicreation.com/sisiden/documentary/{{documentary.slug}}#video"
      },
      "contentLocation": {
        "@type": "Place",
        "name": "{{interview_location}}"
      },
      "citation": "{{sources}}"
    },
    {
      "@type": "BreadcrumbList",
      "itemListElement": [
        { "@type": "ListItem", "position": 1, "name": "SISIDEN",
          "item": "https://sisicreation.com/sisiden/" },
        { "@type": "ListItem", "position": 2, "name": "STORIES",
          "item": "https://sisicreation.com/sisiden/stories/" },
        { "@type": "ListItem", "position": 3, "name": "{{title}}" }
      ]
    }
  ]
}
```

### 設計上の要点

| プロパティ | なぜ入れるか |
|---|---|
| `isPartOf` / `video` → 作品の `@id` | **記事が作品にぶら下がる構造**を機械可読にする。SISIDEN固有の情報設計をそのまま宣言している |
| `mentions` → 人物の `@id` | 「この記事は誰について書かれたか」。人物名での検索・AI回答に効く |
| `about` → 課題の `@id` | 「この記事は何についてか」。ISSUEハブと記事群が1つの知識体系として認識される |
| `author` → 人物ページの `@id` | 執筆者が実在し、プロフィールページを持つこと自体がE-E-A-Tの証明 |
| `contentLocation` | 取材地。一次情報であることのシグナル |
| `dateModified` | AI検索は情報の鮮度を重視する。**実質的な加筆時のみ更新**（誤字修正では触らない） |

### `Article` か `NewsArticle` か

**`Article` を使う。**

`NewsArticle` は速報性のあるニュース向け。SISIDENの記事は
「いま起きたこと」ではなく「記録された物語」であり、数年後も価値が変わらない。
`NewsArticle` にするとGoogle ニュース的な鮮度評価の土俵に乗ってしまい、
ストック型コンテンツとしては不利になる。

インタビュー記事に `Article` のサブタイプを使いたくなるが、
schema.orgに `InterviewArticle` は存在しない。`Article` + `articleSection` で表現する。

---

## 8-5. 人物ページ

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Person",
      "@id": "https://sisicreation.com/sisiden/people/{{slug}}#person",
      "name": "{{name}}",
      "alternateName": "{{name_en}}",
      "jobTitle": "{{title}}",
      "description": "{{lead}}",
      "image": "{{portrait}}",
      "url": "https://sisicreation.com/sisiden/people/{{slug}}",
      "affiliation": {
        "@type": "Organization",
        "name": "{{organizations.name}}"
      },
      "homeLocation": {
        "@type": "Place",
        "name": "{{areas.name}}"
      },
      "subjectOf": [
        { "@id": "https://sisicreation.com/sisiden/documentary/{{documentaries.slug}}#video" }
      ],
      "sameAs": ["{{url_official}}"]
    },
    {
      "@type": "ProfilePage",
      "@id": "https://sisicreation.com/sisiden/people/{{slug}}#profilepage",
      "mainEntity": { "@id": "https://sisicreation.com/sisiden/people/{{slug}}#person" },
      "dateCreated": "{{published_at}}",
      "dateModified": "{{updated_at}}"
    }
  ]
}
```

`subjectOf` で「この人物は、この作品の被写体である」と宣言する。
これにより人物 → 作品 → 記事の三者が構造化データ上でも一つのグラフになる。

---

## 8-6. 社会課題ハブページ

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Article",
      "@id": "https://sisicreation.com/sisiden/issues/{{slug}}#issue",
      "headline": "{{question}}",
      "alternativeHeadline": "{{title}}",
      "description": "{{answer}}",
      "image": "{{hero_image}}",
      "datePublished": "{{published_at}}",
      "dateModified": "{{updated_at}}",
      "inLanguage": "ja",
      "author": { "@id": "https://sisicreation.com/sisiden/#organization" },
      "publisher": { "@id": "https://sisicreation.com/sisiden/#organization" },
      "about": { "@type": "Thing", "name": "{{title}}" },
      "mainEntityOfPage": "https://sisicreation.com/sisiden/issues/{{slug}}"
    },
    {
      "@type": "ItemList",
      "name": "{{title}} に関連するドキュメンタリー",
      "itemListElement": [
        { "@type": "ListItem", "position": 1,
          "url": "https://sisicreation.com/sisiden/documentary/{{documentaries.slug}}" }
      ]
    }
  ]
}
```

### FAQPage について（判断が必要）

ISSUEページの `faq` プロパティに対して `FAQPage` を出すかどうか。

| | 内容 |
|---|---|
| 現状 | GoogleのFAQリッチリザルトは、政府機関・医療機関など**権威性の高いサイトに限定**されている。SISIDENが出しても検索結果に表示される可能性は低い |
| それでも出す価値 | **AI検索側はFAQPageを問答ペアとして解釈しやすい**。リッチリザルト目的ではなく、AI向けの構造宣言として有効 |
| リスク | 中身のないQ&Aを構造化データのためだけに作ると、Googleのスパムポリシー（構造化データの不正使用）に抵触する |

→ **判断: 実際にページ上に表示されているQ&Aがある場合のみ `FAQPage` を出す。**
構造化データのためにQ&Aを捏造しない。これは要件14の
「不自然な構造化データは使用しない」に従う。

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "{{faq.question}}",
      "acceptedAnswer": { "@type": "Answer", "text": "{{faq.answer}}" }
    }
  ]
}
```

---

## 8-7. 一覧ページ / トップページ

### トップページ

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "WebSite",
      "@id": "https://sisicreation.com/sisiden/#website",
      "name": "SISIDEN",
      "alternateName": "シシデン",
      "url": "https://sisicreation.com/sisiden/",
      "description": "物語から、社会を知る。ドキュメンタリー・ストーリー・メディア",
      "publisher": { "@id": "https://sisicreation.com/sisiden/#organization" },
      "inLanguage": "ja"
    },
    {
      "@type": "CollectionPage",
      "@id": "https://sisicreation.com/sisiden/#webpage",
      "isPartOf": { "@id": "https://sisicreation.com/sisiden/#website" }
    }
  ]
}
```

**`SearchAction`（サイトリンク検索ボックス）は入れない。**
サイト内検索を実装するまでは不正確な宣言になる。

### 一覧ページ

`CollectionPage` + `ItemList`。ただし効果は限定的なので、
**Phase 1では BreadcrumbList だけで十分**。

---

## 8-8. STUDIOでの「できる / できない / 代替」

| やりたいこと | STUDIO | 代替 |
|---|---|---|
| 静的ページにJSON-LD | ○ ページ設定 or カスタムコード | - |
| 動的ページにCMS値を差し込んだJSON-LD | ○ 構造化データ欄でプロパティ挿入 | - |
| **マルチ参照（配列）をJSON-LD配列に展開** | **△ 難しい**。`{{issues.slug}}` のような繰り返し展開は標準では想定されていない | **【要確認】実機検証が必要。**できない場合の代替は下記 |
| head内でのCMSプロパティ利用 | ○ 対応 | - |
| ページごとの canonical | ○ | - |
| 日付をISO形式で出力 | **△ 表示形式に依存** | CMSに `*_iso` プロパティを別途持ち、マークアップ用の値を明示的に入力する |

### マルチ参照が配列展開できない場合の代替（重要）

`about` や `mentions` に複数の `@id` を並べる部分が実装できない場合、以下の順で対応する。

| 優先 | 代替案 | 内容 |
|---|---|---|
| 1 | **先頭1件のみ参照** | `about` に主たるISSUEを1件だけ入れる。CMSに `primary_issue`（REF1）を追加し、そこを参照。**情報量は落ちるが正確さは保たれる** |
| 2 | **テキストプロパティに手動でJSON断片を持たせる** | `jsonld_about`（TA型）に `{"@id":"..."},{"@id":"..."}` を編集部が入力。運用負荷が高く、記述ミスのリスクがある。**非推奨** |
| 3 | **Data Connect API 経由に切り替える** | 外部APIから返すJSONをそのまま構造化データに使える（Businessプラン）。本リポジトリの配信APIが対応済み（[付録C](./integration-toolkit.md)） |

→ **Phase 1〜2は優先1（`primary_issue` 1件参照）で運用する。**
構造化データは「少なく正確」が「多く不正確」に勝つ。
内部リンク（HTML上の `<a>`）は全件張られているので、関係性はそちらでも伝わる。

---

## 8-9. 検証手順

公開前に必ず実施する。

| # | ツール | 確認内容 |
|---|---|---|
| 1 | [Schema Markup Validator](https://validator.schema.org/) | 構文エラー・未定義プロパティ |
| 2 | [Google リッチリザルトテスト](https://search.google.com/test/rich-results) | Google側の解釈。VideoObject / Article / Breadcrumb |
| 3 | GSC > 拡張 | 公開後のエラー継続監視 |
| 4 | 本リポジトリ `scripts/media_export.py --format jsonld` | 正本データからJSON-LDを生成し、STUDIO出力と突き合わせる |

### 公開前チェックリスト

- [ ] `@id` のURLが実在するURLと一致しているか（末尾スラッシュの揺れに注意）
- [ ] 日付が ISO 8601 形式（`2026-09-20`）で出力されているか
- [ ] `duration` が `PT11M24S` 形式か
- [ ] ページ上に表示されていない情報をマークアップしていないか ← **最重要**
- [ ] 画像URLが絶対URLか
- [ ] `author` が実在の人物ページにリンクしているか
