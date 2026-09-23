import { getCollection, type CollectionEntry } from "astro:content";
import categories from "../data/categories.json";

export type Article = CollectionEntry<"articles">;

const showDrafts = import.meta.env.DEV || process.env.SHOW_DRAFTS === "1";

export async function getArticles(): Promise<Article[]> {
  const all = await getCollection("articles", (a) => showDrafts || !a.data.draft);
  return all.sort((a, b) => b.data.updated.getTime() - a.data.updated.getTime());
}

export function getCategory(slug: string) {
  return categories.find((c) => c.slug === slug);
}

export function formatDate(d: Date): string {
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export const tools = [
  {
    slug: "cost-simulator",
    name: "外注費シミュレーター",
    description: "社員採用・制作会社・フリーランスの年間コストを、自社の条件で比べます。",
  },
  {
    slug: "brief-generator",
    name: "発注内容整理ジェネレーター",
    description: "目的・納期・予算・成果物・修正回数を入れると、発注メールの下書きを作ります。",
  },
  {
    slug: "interview-scoresheet",
    name: "外注先面談スコアシート",
    description: "候補者を7つの観点で採点し、比べられるようにします。印刷もできます。",
  },
  {
    slug: "checklist",
    name: "発注前チェックリスト",
    description: "発注の前に決めておくこと・相手に伝えることを、抜け漏れなく確認します。",
  },
  {
    slug: "diagnosis",
    name: "外注先選び診断",
    description: "制作会社・フリーランス・クラウドソーシング・エージェント・知人紹介のどれが合うかを診断します。",
  },
];
