"""WordPress WXR (eXtended RSS) を生成する。

STUDIO CMS はCSVの直接インポートには非対応だが、WordPressのXMLからの
一括インポートには対応している。記事の初期投入をこの経路で行う。

制約（docs/sisiden-media/integration-toolkit.md にも記載）:
  WXRが表現できるのは タイトル / 本文 / 抜粋 / 公開日 / スラッグ /
  カテゴリ / タグ / 著者名 まで。作品・人物・社会課題へのリレーションは
  WXRの語彙に存在しないため、インポート後にSTUDIO上で接続し直す必要がある。
  そのため本文末尾に「この記事について」ブロックを埋め込み、
  取材情報が失われないようにしている。
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..content import Repository, _as_list

WXR_VERSION = "1.2"
RFC822 = "%a, %d %b %Y %H:%M:%S +0000"


def _cdata(text: Any) -> str:
    value = "" if text is None else str(text)
    # CDATAセクション内に ]]> を含められないため分割する
    value = value.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{value}]]>"


def _rfc822(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    return dt.strftime(RFC822)


def _wp_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return f"{value.isoformat()} 00:00:00"
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def markdown_to_html(text: str) -> str:
    """本文の最小限のMarkdown記法をHTMLへ変換する。"""
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", text.strip())
    out: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if block.startswith("### "):
            out.append(f"<h4>{html.escape(block[4:].strip())}</h4>")
        elif block.startswith("## "):
            out.append(f"<h3>{html.escape(block[3:].strip())}</h3>")
        elif block.startswith("# "):
            out.append(f"<h2>{html.escape(block[2:].strip())}</h2>")
        elif block.startswith("> "):
            quote = " ".join(line[2:].strip() for line in block.splitlines())
            out.append(f"<blockquote><p>{html.escape(quote)}</p></blockquote>")
        else:
            out.append(f"<p>{html.escape(block).replace(chr(10), '<br />')}</p>")
    return "\n".join(out)


def _about_block(repo: Repository, item: dict[str, Any]) -> str:
    author = repo.get("people", item.get("author") or "")
    supervisor = repo.get("people", item.get("supervisor") or "")
    rows = [
        ("取材日", item.get("interview_date")),
        ("取材場所", item.get("interview_location")),
        ("取材対象", item.get("interview_subjects")),
        ("取材・文", author["name"] if author else None),
        ("撮影", item.get("photographer")),
        ("編集", item.get("editor")),
        ("監修", supervisor["name"] if supervisor else None),
    ]
    lines = [
        f"<li>{html.escape(label)}: {html.escape(str(value))}</li>"
        for label, value in rows if value
    ]
    location = item.get("interview_location") or ""
    interview_date = item.get("interview_date")
    date_text = interview_date.isoformat() if isinstance(interview_date, date) else ""
    return (
        '<div class="sisiden-about">'
        "<h3>この記事について</h3>"
        f"<p>この記事は、SISIDENが{html.escape(location)}で{html.escape(date_text)}に"
        "行った取材をもとに制作しています。</p>"
        f"<ul>{''.join(lines)}</ul>"
        "</div>"
    )


def _item_xml(repo: Repository, item: dict[str, Any], post_id: int) -> str:
    slug = item["slug"]
    category = repo.get("categories", item.get("category") or "")
    author = repo.get("people", item.get("author") or "")
    body = markdown_to_html(item.get("body", "")) + "\n" + _about_block(repo, item)

    terms = []
    if category:
        terms.append(
            f'      <category domain="category" nicename="{html.escape(category["slug"])}">'
            f'{_cdata(category["name_ja"])}</category>'
        )
    for tag_slug in _as_list(item.get("tags")):
        tag = repo.get("tags", tag_slug)
        if tag:
            terms.append(
                f'      <category domain="post_tag" nicename="{html.escape(tag_slug)}">'
                f'{_cdata(tag["name"])}</category>'
            )

    meta_fields = [
        ("sisiden_documentary", item.get("documentary")),
        ("sisiden_people", ",".join(_as_list(item.get("people")))),
        ("sisiden_issues", ",".join(_as_list(item.get("issues")))),
        ("sisiden_areas", ",".join(_as_list(item.get("areas")))),
        ("sisiden_interview_date", item.get("interview_date")),
        ("sisiden_interview_location", item.get("interview_location")),
        ("sisiden_interview_subjects", item.get("interview_subjects")),
        ("sisiden_author", item.get("author")),
        ("sisiden_hero_image", item.get("hero_image")),
    ]
    metas = [
        "      <wp:postmeta>\n"
        f"        <wp:meta_key>{_cdata(key)}</wp:meta_key>\n"
        f"        <wp:meta_value>{_cdata(value)}</wp:meta_value>\n"
        "      </wp:postmeta>"
        for key, value in meta_fields if value
    ]

    return "\n".join([
        "    <item>",
        f"      <title>{_cdata(item.get('title'))}</title>",
        f"      <link>{html.escape(repo.url_for('articles', slug))}</link>",
        f"      <pubDate>{_rfc822(item.get('published_at'))}</pubDate>",
        f"      <dc:creator>{_cdata(author['name'] if author else 'SISIDEN')}</dc:creator>",
        f'      <guid isPermaLink="false">{html.escape(repo.url_for("articles", slug))}</guid>',
        "      <description></description>",
        f"      <content:encoded>{_cdata(body)}</content:encoded>",
        f"      <excerpt:encoded>{_cdata(item.get('lead'))}</excerpt:encoded>",
        f"      <wp:post_id>{post_id}</wp:post_id>",
        f"      <wp:post_date>{_wp_date(item.get('published_at'))}</wp:post_date>",
        f"      <wp:post_date_gmt>{_wp_date(item.get('published_at'))}</wp:post_date_gmt>",
        "      <wp:comment_status>closed</wp:comment_status>",
        "      <wp:ping_status>closed</wp:ping_status>",
        f"      <wp:post_name>{html.escape(slug)}</wp:post_name>",
        "      <wp:status>publish</wp:status>",
        "      <wp:post_parent>0</wp:post_parent>",
        f"      <wp:menu_order>{post_id}</wp:menu_order>",
        "      <wp:post_type>post</wp:post_type>",
        "      <wp:is_sticky>0</wp:is_sticky>",
        *terms,
        *metas,
        "    </item>",
    ])


def export_articles(repo: Repository, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "articles.wxr.xml"
    site = repo.schema.site
    base = site["base_url"].rstrip("/")

    categories = [
        "    <wp:category>\n"
        f"      <wp:category_nicename>{html.escape(c['slug'])}</wp:category_nicename>\n"
        "      <wp:category_parent></wp:category_parent>\n"
        f"      <wp:cat_name>{_cdata(c['name_ja'])}</wp:cat_name>\n"
        "    </wp:category>"
        for c in repo.model_items("categories")
    ]
    tags = [
        "    <wp:tag>\n"
        f"      <wp:tag_slug>{html.escape(t['slug'])}</wp:tag_slug>\n"
        f"      <wp:tag_name>{_cdata(t['name'])}</wp:tag_name>\n"
        "    </wp:tag>"
        for t in repo.model_items("tags")
    ]
    items = [
        _item_xml(repo, item, i + 1)
        for i, item in enumerate(repo.model_items("articles"))
    ]

    xml = "\n".join([
        '<?xml version="1.0" encoding="UTF-8" ?>',
        '<rss version="2.0"',
        '  xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"',
        '  xmlns:content="http://purl.org/rss/1.0/modules/content/"',
        '  xmlns:wfw="http://wellformedweb.org/CommentAPI/"',
        '  xmlns:dc="http://purl.org/dc/elements/1.1/"',
        '  xmlns:wp="http://wordpress.org/export/1.2/">',
        "  <channel>",
        f"    <title>{_cdata(site['name'])}</title>",
        f"    <link>{html.escape(base)}/</link>",
        f"    <description>{_cdata(site.get('tagline'))}</description>",
        f"    <pubDate>{_rfc822(None)}</pubDate>",
        "    <language>ja</language>",
        f"    <wp:wxr_version>{WXR_VERSION}</wp:wxr_version>",
        f"    <wp:base_site_url>{html.escape(base)}/</wp:base_site_url>",
        f"    <wp:base_blog_url>{html.escape(base)}/</wp:base_blog_url>",
        *categories,
        *tags,
        *items,
        "  </channel>",
        "</rss>",
        "",
    ])

    path.write_text(xml, encoding="utf-8")
    return path
