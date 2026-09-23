// @ts-check
import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";

// 公開ドメインは未決定(DECISIONS D-009)。決まったらこの1行を差し替える。
const SITE_URL = process.env.SITE_URL || "https://hacchu-os.example";

export default defineConfig({
  site: SITE_URL,
  trailingSlash: "always",
  integrations: [
    mdx(),
    sitemap({
      // 広告リダイレクト(/go/)は検索結果に出さない
      filter: (page) => !page.includes("/go/"),
    }),
  ],
});
