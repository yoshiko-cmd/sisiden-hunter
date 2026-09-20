# STEP 3. サイトマップ

## 3-1. 全体ツリー

`S` = 静的ページ / `D` = 動的ページ（CMS詳細）/ `L` = 一覧ページ

```
sisicreation.com
│
├─ （既存コーポレートサイト）                              ※ 触らない
│
└─ /sisiden/                                    S   SISIDEN MEDIA トップ
   │
   ├─ /sisiden/documentary/                     L   作品一覧
   │  └─ /sisiden/documentary/:slug             D   作品詳細              ★最重要
   │
   ├─ /sisiden/stories/                         L   記事一覧（全カテゴリ）
   │  └─ /sisiden/stories/:slug                 D   記事詳細
   │
   ├─ /sisiden/category/:slug                   D   カテゴリ別記事一覧      ※CATEGORIESの動的ページ
   │     ├ /sisiden/category/interview              証言
   │     ├ /sisiden/category/field-note             取材ノート
   │     ├ /sisiden/category/social-issue           社会の構造
   │     ├ /sisiden/category/local-context          地域の文脈
   │     ├ /sisiden/category/insight                洞察
   │     └ /sisiden/category/after-story            その後
   │
   ├─ /sisiden/people/                          L   人物一覧
   │  └─ /sisiden/people/:slug                  D   人物詳細
   │
   ├─ /sisiden/issues/                          L   社会課題一覧
   │  └─ /sisiden/issues/:slug                  D   社会課題ハブ           ★AIO最重要
   │
   ├─ /sisiden/areas/                           L   地域一覧
   │  └─ /sisiden/areas/:slug                   D   地域ハブ
   │
   ├─ /sisiden/organizations/                   L   企業・団体一覧
   │  └─ /sisiden/organizations/:slug           D   組織ページ（Phase 2）
   │
   ├─ /sisiden/tags/:slug                       D   タグ別一覧（noindex）
   │
   ├─ /sisiden/about/                           S   SISIDENについて       ★E-E-A-T
   │  ├─ /sisiden/about/editorial-policy/       S   編集方針
   │  ├─ /sisiden/about/reporting-policy/       S   取材ポリシー
   │  └─ /sisiden/about/team/                   S   編集部・制作チーム
   │
   ├─ /sisiden/producer/                        S   FROM THE PRODUCER（連載ハブ）
   │
   └─ /sisiden/contact/                         S   取材依頼・お問い合わせ
```

## 3-2. ページ数カウント（STUDIO 300ページ上限に対して）

STUDIOでは**動的ページはテンプレート1枚で1ページ**として数える。
CMSアイテムが1,000件あっても消費は1。

| 種別 | ページ | 枚数 |
|---|---|---|
| S 静的 | トップ / about×4 / producer / contact | 7 |
| L 一覧 | documentary / stories / people / issues / areas / organizations | 6 |
| D 動的 | documentary詳細 / stories詳細 / category / people詳細 / issues詳細 / areas詳細 / organizations詳細 / tags | 8 |
| その他 | 404（共用） | 0〜1 |
| **合計** | | **21〜22** |

→ 300ページ上限に対して余裕は十分。**コーポレート側の既存ページ数と合算しても問題にならない。**
むしろ制約になるのは **CMSモデル数10** と **CMSアイテム5,000**（[STEP 1-2 論点C](./01-current-site-analysis.md)）。

## 3-3. Phase 分割

一度に全部作らない。**Phase 1で価値が出る最小構成**を定義する。

### Phase 1（初期公開 / 約4〜6週）

```
/sisiden/                        トップ
/sisiden/documentary/            作品一覧
/sisiden/documentary/:slug       作品詳細          ← ここが核
/sisiden/stories/                記事一覧
/sisiden/stories/:slug           記事詳細
/sisiden/people/                 人物一覧
/sisiden/people/:slug            人物詳細
/sisiden/about/                  SISIDENについて
```

必要モデル: DOCUMENTARIES / ARTICLES / PEOPLE / CATEGORIES（4モデル）
初期コンテンツ目標: **作品3本 × 記事3本 = 9記事 + 人物6名**

記事を広く薄く並べるより、**1作品を完全な形で見せる**ほうがメディアの思想が伝わる。
最初の公開は「TONKAN の完全版」1つで成立する。

### Phase 2（+4週）

```
/sisiden/issues/                 社会課題一覧
/sisiden/issues/:slug            社会課題ハブ      ← AIO の主戦場
/sisiden/category/:slug          カテゴリ別一覧
/sisiden/about/editorial-policy/  編集方針
/sisiden/about/reporting-policy/  取材ポリシー
```

追加モデル: ISSUES / TAGS
ISSUEは**3本だけ**本気で作る。20本の薄いハブより3本の決定版。

### Phase 3（+8週〜）

```
/sisiden/areas/  /sisiden/areas/:slug
/sisiden/organizations/
/sisiden/producer/
/sisiden/contact/
サイト内検索
```

追加モデル: AREAS / ORGANIZATIONS

### Phase 4（記事300本〜 / 独立ドメイン検討）

- `sisiden.jp` への移行判断（[STEP 4-6](./04-url-design.md)）
- Data Connect API による外部データソース化（[STEP 5 方式B](./05-studio-cms-model.md)）
- 英語版（`/en/`）

## 3-4. 一覧ページの表示ロジック

| ページ | デフォルト並び順 | 表示件数 | 絞り込み |
|---|---|---|---|
| /documentary/ | 公開日 降順 | 全件（12件ずつ） | 社会課題 / 地域 |
| /stories/ | 公開日 降順 | 12件ずつ | カテゴリ / 作品 |
| /people/ | 50音順 または 登場作品数 降順 | 全件 | 役割（主人公/専門家/制作） |
| /issues/ | 編集部の並び順（手動） | 全件 | なし |
| /areas/ | 地方ブロック別グルーピング | 全件 | なし |
| /category/:slug | 公開日 降順 | 12件ずつ | なし |

STUDIOの動的リストは**ページネーションと「もっと見る」の両方に対応**。
記事100本を超えたら「もっと見る」よりページネーションを推奨（`?page=2` がクロールされるため）。

## 3-5. XMLサイトマップ

STUDIOは `/sitemap.xml` を自動生成する。
確認すべきは以下。

- [ ] `noindex` 指定したタグページがサイトマップから除外されているか
- [ ] CMS詳細ページが全件含まれているか
- [ ] コーポレート側のページと同一サイトマップに同居する形になるか（同一プロジェクトなら同居する）

**同居は問題ない。**むしろ同一サイト内にSISIDENがあることをGoogleに正しく伝えられる。
将来の独立時にサイトマップを分割する。
