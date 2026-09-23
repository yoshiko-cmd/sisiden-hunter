# 発注OS(仮称)

発注者向け外注実務メディア。Astro + MDX の静的サイト。

```bash
cd hacchu-os
npm install
npm run dev              # http://localhost:4321 (草稿も表示)
npm run build            # dist/ に本番用の静的ファイル(草稿は除外)
npm run check:content    # 記事の品質チェック
node scripts/build-keywords.mjs   # キーワード台帳の再生成
```

- 記事: `src/content/articles/*.mdx`(frontmatterの項目は `src/content.config.ts`)
- サイト名・フォーム送信先: `src/data/site.json`
- 広告リンク: `src/data/offers.json`(url を入れるとPR付きリンクと `/go/<id>/` が有効になる)
- 運用ドキュメント: `docs/`(作業再開時は PROJECT → BACKLOG → BLOCKED → DECISIONS)
