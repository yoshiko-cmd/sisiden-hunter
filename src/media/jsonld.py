"""正本データからJSON-LDを生成する。

STUDIOの構造化データ欄では、マルチ参照を配列として展開することが難しい
(docs/sisiden-media/08-structured-data.md 8-8)。ここで完成形のJSON-LDを
組み立てておけば、Data Connect API経由でそのまま差し込める。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .content import Repository, _as_list

CONTEXT = "https://schema.org"


def _iso(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else None


def _org_id(repo: Repository) -> str:
    return f"{repo.schema.site['base_url'].rstrip('/')}/#organization"


def _node_id(repo: Repository, model: str, slug: str, fragment: str) -> str:
    return f"{repo.url_for(model, slug)}#{fragment}"


def _refs_to_ids(repo: Repository, item: dict[str, Any], prop: str,
                 model: str, fragment: str) -> list[dict[str, str]]:
    ids = []
    for slug in _as_list(item.get(prop)):
        if repo.get(model, slug) is not None:
            ids.append({"@id": _node_id(repo, model, slug, fragment)})
    return ids


def _compact(node: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in node.items() if v not in (None, "", [], {})}


def breadcrumb(repo: Repository, trail: list[tuple[str, str | None]]) -> dict[str, Any]:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            _compact({
                "@type": "ListItem",
                "position": i + 1,
                "name": name,
                "item": url,
            })
            for i, (name, url) in enumerate(trail)
        ],
    }


def organization(repo: Repository) -> dict[str, Any]:
    site = repo.schema.site
    base = site["base_url"].rstrip("/")
    return _compact({
        "@context": CONTEXT,
        "@type": "Organization",
        "@id": _org_id(repo),
        "name": site["name"],
        "alternateName": site.get("alternate_names", []),
        "url": f"{base}/",
        "description": site.get("description"),
        "parentOrganization": _compact({
            "@type": "Organization",
            "name": site.get("publisher"),
            "url": site.get("publisher_url"),
        }),
        "sameAs": site.get("same_as", []),
    })


def website(repo: Repository) -> dict[str, Any]:
    site = repo.schema.site
    base = site["base_url"].rstrip("/")
    return _compact({
        "@context": CONTEXT,
        "@type": "WebSite",
        "@id": f"{base}/#website",
        "name": site["name"],
        "alternateName": site.get("name_ja"),
        "url": f"{base}/",
        "description": site.get("tagline"),
        "publisher": {"@id": _org_id(repo)},
        "inLanguage": "ja",
    })


def documentary(repo: Repository, item: dict[str, Any]) -> dict[str, Any]:
    slug = item["slug"]
    base = repo.schema.site["base_url"].rstrip("/")
    video = _compact({
        "@type": "VideoObject",
        "@id": _node_id(repo, "documentaries", slug, "video"),
        "name": f"{item['title']}｜{item.get('subtitle', '')}".rstrip("｜"),
        "description": item.get("lead"),
        "thumbnailUrl": item.get("key_visual"),
        "uploadDate": _iso(item.get("published_at")),
        "duration": item.get("duration_iso8601"),
        "embedUrl": f"https://www.youtube.com/embed/{item['youtube_id']}"
        if item.get("youtube_id") else None,
        "url": repo.url_for("documentaries", slug),
        "publisher": {"@id": _org_id(repo)},
        "creator": {"@id": _org_id(repo)},
        "director": _compact({"@type": "Person", "name": item.get("credit_direction")}),
        "about": _refs_to_ids(repo, item, "issues", "issues", "issue"),
        "actor": _refs_to_ids(repo, item, "people", "people", "person"),
        "contentLocation": _compact({"@type": "Place", "name": item.get("shoot_location")}),
        "inLanguage": "ja",
    })
    return {
        "@context": CONTEXT,
        "@graph": [
            video,
            breadcrumb(repo, [
                ("SISIDEN", f"{base}/"),
                ("DOCUMENTARIES", f"{base}/documentary/"),
                (item["title"], None),
            ]),
        ],
    }


def article(repo: Repository, item: dict[str, Any]) -> dict[str, Any]:
    slug = item["slug"]
    base = repo.schema.site["base_url"].rstrip("/")
    category = repo.get("categories", item.get("category") or "")
    doc_slug = item.get("documentary")
    author_slug = item.get("author")

    node = _compact({
        "@type": "Article",
        "@id": _node_id(repo, "articles", slug, "article"),
        "headline": item.get("title"),
        "description": item.get("lead"),
        "image": item.get("hero_image"),
        "datePublished": _iso(item.get("published_at")),
        "dateModified": _iso(item.get("updated_at") or item.get("published_at")),
        "inLanguage": "ja",
        "isAccessibleForFree": True,
        "author": {"@id": _node_id(repo, "people", author_slug, "person")}
        if author_slug and repo.get("people", author_slug) else None,
        "publisher": {"@id": _org_id(repo)},
        "mainEntityOfPage": repo.url_for("articles", slug),
        "articleSection": category.get("name_ja") if category else None,
        "about": _refs_to_ids(repo, item, "issues", "issues", "issue"),
        "mentions": _refs_to_ids(repo, item, "people", "people", "person"),
        "isPartOf": {"@id": _node_id(repo, "documentaries", doc_slug, "video")}
        if doc_slug and repo.get("documentaries", doc_slug) else None,
        "video": {"@id": _node_id(repo, "documentaries", doc_slug, "video")}
        if doc_slug and repo.get("documentaries", doc_slug) else None,
        "contentLocation": _compact({
            "@type": "Place", "name": item.get("interview_location")
        }),
    })
    return {
        "@context": CONTEXT,
        "@graph": [
            node,
            breadcrumb(repo, [
                ("SISIDEN", f"{base}/"),
                ("STORIES", f"{base}/stories/"),
                (item.get("title"), None),
            ]),
        ],
    }


def person(repo: Repository, item: dict[str, Any]) -> dict[str, Any]:
    slug = item["slug"]
    same_as = [u.strip() for u in (item.get("url_social") or "").splitlines() if u.strip()]
    if item.get("url_official"):
        same_as.insert(0, item["url_official"])

    org_names = [
        repo.get("organizations", s)["name"]
        for s in _as_list(item.get("organizations"))
        if repo.get("organizations", s)
    ]
    area_names = [
        repo.get("areas", s)["name"]
        for s in _as_list(item.get("areas"))
        if repo.get("areas", s)
    ]

    node = _compact({
        "@type": "Person",
        "@id": _node_id(repo, "people", slug, "person"),
        "name": item.get("name"),
        "alternateName": item.get("name_en"),
        "jobTitle": item.get("title"),
        "description": item.get("lead"),
        "image": item.get("portrait"),
        "url": repo.url_for("people", slug),
        "affiliation": [{"@type": "Organization", "name": n} for n in org_names],
        "homeLocation": [{"@type": "Place", "name": n} for n in area_names],
        "subjectOf": _refs_to_ids(repo, item, "documentaries", "documentaries", "video"),
        "sameAs": same_as,
    })
    return {
        "@context": CONTEXT,
        "@graph": [
            node,
            _compact({
                "@type": "ProfilePage",
                "@id": _node_id(repo, "people", slug, "profilepage"),
                "mainEntity": {"@id": _node_id(repo, "people", slug, "person")},
                "dateCreated": _iso(item.get("published_at")),
                "dateModified": _iso(item.get("updated_at")),
            }),
        ],
    }


def issue(repo: Repository, item: dict[str, Any]) -> dict[str, Any]:
    slug = item["slug"]
    node = _compact({
        "@type": "Article",
        "@id": _node_id(repo, "issues", slug, "issue"),
        "headline": item.get("question"),
        "alternativeHeadline": item.get("title"),
        "description": item.get("answer"),
        "image": item.get("hero_image"),
        "datePublished": _iso(item.get("published_at")),
        "dateModified": _iso(item.get("updated_at")),
        "inLanguage": "ja",
        "author": {"@id": _org_id(repo)},
        "publisher": {"@id": _org_id(repo)},
        "about": _compact({"@type": "Thing", "name": item.get("title")}),
        "mainEntityOfPage": repo.url_for("issues", slug),
    })

    related = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "url": repo.url_for("documentaries", s),
        }
        for i, s in enumerate(_as_list(item.get("documentaries")))
        if repo.get("documentaries", s)
    ]

    graph: list[dict[str, Any]] = [node]
    if related:
        graph.append({
            "@type": "ItemList",
            "name": f"{item.get('title')} に関連するドキュメンタリー",
            "itemListElement": related,
        })
    return {"@context": CONTEXT, "@graph": graph}


BUILDERS = {
    "documentaries": documentary,
    "articles": article,
    "people": person,
    "issues": issue,
}


def build(repo: Repository, model_name: str, item: dict[str, Any]) -> dict[str, Any] | None:
    builder = BUILDERS.get(model_name)
    return builder(repo, item) if builder else None
