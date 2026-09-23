// 記事の品質チェック(docs/CONTENT_PLAN.md「公開前の品質チェック」のうち機械的に確認できる項目)。
// 使い方: npm run check:content   エラーがあれば終了コード1。
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const articleDir = join(root, "src/content/articles");
const toolDir = join(root, "src/pages/tools");
const categories = JSON.parse(readFileSync(join(root, "src/data/categories.json"), "utf8"));
const offers = JSON.parse(readFileSync(join(root, "src/data/offers.json"), "utf8")).offers;

// 断定・誇大・体験の捏造につながりやすい表現
const banned = [
  { re: /使ってみた/, why: "使用経験の記載は運営者の実体験がある場合のみ(要確認)" },
  { re: /絶対に?(安全|大丈夫|違法にならない|儲かる)/, why: "断定表現" },
  { re: /違法になりません|合法です/, why: "法的な断定表現" },
  { re: /No\.?1|業界最安|日本一/, why: "根拠のない最上級表現" },
  { re: /利用者の声|口コミ(では|によると)/, why: "利用者の声は実在・出典がある場合のみ" },
];
const legalWords = /フリーランス法|契約|源泉徴収|インボイス|著作権|税/;

const slugs = readdirSync(articleDir).filter((f) => /\.mdx?$/.test(f)).map((f) => f.replace(/\.mdx?$/, ""));
const toolSlugs = readdirSync(toolDir).filter((f) => f.endsWith(".astro") && f !== "index.astro").map((f) => f.replace(".astro", ""));

function frontmatter(src) {
  const m = src.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return {};
  const fm = {};
  for (const line of m[1].split("\n")) {
    const kv = line.match(/^([a-zA-Z]+):\s*(.*)$/);
    if (kv) fm[kv[1]] = kv[2].replace(/^"|"$/g, "");
  }
  fm._raw = m[1];
  return fm;
}

let errors = 0;
let warnings = 0;
const report = [];

for (const slug of slugs) {
  const file = readdirSync(articleDir).find((f) => f.startsWith(slug + "."));
  const src = readFileSync(join(articleDir, file), "utf8");
  const fm = frontmatter(src);
  const body = src.slice(src.indexOf("---", 3) + 3);
  const draft = fm.draft === "true";
  const issues = [];
  const err = (msg) => issues.push(["ERROR", msg]);
  const warn = (msg) => issues.push(["WARN", msg]);

  // 構造
  for (const key of ["title", "description", "summary", "category", "published", "updated"]) {
    if (!fm[key]) err(`frontmatter ${key} がない`);
  }
  if (fm.category && !categories.some((c) => c.slug === fm.category)) err(`未知のcategory: ${fm.category}`);
  if (fm.subcategory) {
    const cat = categories.find((c) => c.slug === fm.category);
    if (cat && !cat.children.some((c) => c.slug === fm.subcategory)) err(`未知のsubcategory: ${fm.subcategory}`);
  }
  if (fm.summary && fm.summary.length < 40) warn("冒頭の結論(summary)が短い");

  // 広告表示
  // URL登録済み(=実際に広告リンクになる)のオファーを使う記事は、hasAds: true が必須
  const offerIds = [...body.matchAll(/<OfferLink\s+id="([^"]+)"/g)].map((m) => m[1]);
  for (const id of offerIds) if (!offers.some((o) => o.id === id)) err(`offers.json に無いオファー: ${id}`);
  const liveAds = offerIds.filter((id) => offers.find((o) => o.id === id)?.url);
  if (liveAds.length && fm.hasAds !== "true") err(`広告リンク(${liveAds.join(", ")})があるのに hasAds: true がない(広告表示が出ない)`);
  if (/rel="sponsored/.test(body)) err("広告リンクは OfferLink コンポーネント経由にする(PR表示のため)");

  // 法務・税務
  if (legalWords.test(fm.title + fm.summary) && ["contract", "payment"].includes(fm.category) && fm.expertReview !== "recommended" && fm.expertReview !== "done") {
    warn("法務・税務の記事だが expertReview が設定されていない");
  }
  if (fm.expertReview === "recommended" && !/sources:\n\s+- /.test(fm._raw)) err("専門家レビュー推奨の記事に出典(sources)がない");

  // 一次情報
  const placeholders = (body.match(/<Firsthand\b|\[運営者一次情報追加予定\]/g) || []).length;
  if (placeholders && fm.needsFirsthand !== "true") err("一次情報の枠があるのに needsFirsthand: true がない");
  if (!placeholders && fm.needsFirsthand === "true") warn("needsFirsthand: true だが一次情報の枠がない(埋め終わったら false に)");

  // 未確認の数字
  if (!draft && /\[公式で最新確認予定\]|\[確認予定\]/.test(body)) err("未確認の値が残ったまま公開対象になっている");

  // 禁止表現
  for (const b of banned) if (b.re.test(body) || b.re.test(fm.summary || "")) warn(`表現の確認: ${b.re} — ${b.why}`);

  // 内部リンク
  const links = [...body.matchAll(/\]\((\/[^)\s]*)\)|href="(\/[^"]*)"/g)].map((m) => m[1] || m[2]);
  if (links.length === 0 && !/related: \[.+\]/.test(fm._raw)) warn("内部リンクがない");
  for (const l of links) {
    const a = l.match(/^\/articles\/([^/]+)\/$/);
    const t = l.match(/^\/tools\/([^/]+)\/$/);
    if (a && !slugs.includes(a[1])) err(`リンク切れ: ${l}`);
    if (t && !toolSlugs.includes(t[1])) err(`リンク切れ: ${l}`);
    if ((l.startsWith("/articles/") || l.startsWith("/tools/")) && !l.endsWith("/")) warn(`末尾スラッシュなし: ${l}`);
  }
  const related = (fm._raw.match(/related: \[(.*)\]/) || [, ""])[1].match(/"([^"]+)"/g) || [];
  for (const r of related.map((s) => s.replace(/"/g, ""))) if (!slugs.includes(r)) err(`related に存在しない記事: ${r}`);
  const tools = (fm._raw.match(/tools: \[(.*)\]/) || [, ""])[1].match(/"([^"]+)"/g) || [];
  for (const t of tools.map((s) => s.replace(/"/g, ""))) if (!toolSlugs.includes(t)) err(`tools に存在しないツール: ${t}`);

  // FAQ(AIO向け)
  if (!draft && !/faq:\n\s+- q:/.test(fm._raw)) warn("FAQがない");

  const e = issues.filter((i) => i[0] === "ERROR").length;
  errors += e;
  warnings += issues.length - e;
  report.push({ slug, draft, placeholders, issues });
}

for (const r of report) {
  const status = r.issues.some((i) => i[0] === "ERROR") ? "NG" : r.issues.length ? "注意" : "OK";
  console.log(`${status.padEnd(3)} ${r.slug}${r.draft ? " (草稿)" : ""}${r.placeholders ? ` 一次情報枠${r.placeholders}` : ""}`);
  for (const [level, msg] of r.issues) console.log(`     ${level}: ${msg}`);
}
console.log(`\n記事 ${report.length}本(公開対象 ${report.filter((r) => !r.draft).length}本) / エラー ${errors} / 注意 ${warnings}`);
if (!existsSync(join(root, "docs/QUALITY_CHECKLIST.md"))) console.log("※ 人による確認項目は docs/QUALITY_CHECKLIST.md");
process.exit(errors ? 1 : 0);
