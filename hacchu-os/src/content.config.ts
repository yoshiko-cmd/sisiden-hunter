import { defineCollection } from "astro:content";
import { glob } from "astro/loaders";
import { z } from "astro/zod";

const articles = defineCollection({
  loader: glob({ pattern: "**/*.{md,mdx}", base: "./src/content/articles" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    // categories.json の slug
    category: z.string(),
    subcategory: z.string().optional(),
    // 記事冒頭に出す結論(AIO: 最初に答える)
    summary: z.string(),
    published: z.coerce.date(),
    updated: z.coerce.date(),
    author: z.string().default("発注OS編集部"),
    // 広告リンクを含むか。true なら冒頭に広告表示を出す
    hasAds: z.boolean().default(false),
    // 法務・税務など、専門家レビューを推奨する記事
    expertReview: z.enum(["none", "recommended", "done"]).default("none"),
    reviewer: z.string().optional(),
    // 運営者の一次情報が未取得の箇所が残っているか
    needsFirsthand: z.boolean().default(false),
    // 草稿は本番ビルドに含めない(SHOW_DRAFTS=1 で確認できる)
    draft: z.boolean().default(false),
    sources: z
      .array(z.object({ title: z.string(), url: z.string().url(), publisher: z.string() }))
      .default([]),
    faq: z.array(z.object({ q: z.string(), a: z.string() })).default([]),
    related: z.array(z.string()).default([]),
    tools: z.array(z.string()).default([]),
  }),
});

export const collections = { articles };
