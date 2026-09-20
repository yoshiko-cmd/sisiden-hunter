"""STUDIO Data Connect API に返すJSONを組み立てる。

レスポンス形状は microCMS に合わせている（STUDIOがmicroCMSを公式サポート
しているため、同じ形なら接続設定で迷わない）。

  一覧: {"contents": [...], "totalCount": n, "offset": 0, "limit": 20}
  詳細: {...}

リレーションは参照先の要約オブジェクトとして埋め込む。STUDIO側で
ネストした値をそのままバインドできるため、追加のAPI呼び出しが要らない。

各アイテムには `jsonld` を文字列で同梱する。STUDIOの構造化データ欄は
マルチ参照の配列展開が難しいため、完成済みのJSON-LDを渡してしまう。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from ..content import Repository, _as_list
from .. import jsonld

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

SUMMARY_FIELDS = {
    "documentaries": ("title", "subtitle", "key_visual", "portrait_visual", "duration"),
    "articles": ("title", "lead", "hero_image"),
    "people": ("name", "title", "portrait"),
    "issues": ("title", "question", "answer", "hero_image"),
    "areas": ("name", "prefecture"),
    "organizations": ("name", "org_type"),
    "categories": ("number", "name_en", "name_ja"),
    "tags": ("name",),
}


def _scalar(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def summarize(repo: Repository, model_name: str, slug: str) -> dict[str, Any] | None:
    item = repo.get(model_name, slug)
    if item is None:
        return None
    summary = {"slug": slug, "url": repo.url_for(model_name, slug)}
    for field in SUMMARY_FIELDS.get(model_name, ()):
        if item.get(field) is not None:
            summary[field] = _scalar(item[field])
    return summary


def serialize(repo: Repository, model_name: str, item: dict[str, Any],
              embed_refs: bool = True) -> dict[str, Any]:
    model = repo.schema.model(model_name)
    out: dict[str, Any] = {
        "id": item["slug"],
        "slug": item["slug"],
        "url": repo.url_for(model_name, item["slug"]),
    }

    for prop in model.properties:
        value = item.get(prop.name)
        if value is None:
            continue
        if prop.is_ref and embed_refs:
            summaries = [
                s for s in (summarize(repo, prop.ref_target, ref) for ref in _as_list(value))
                if s is not None
            ]
            out[prop.name] = summaries[0] if prop.is_single_ref else summaries
        elif prop.is_ref:
            out[prop.name] = value
        else:
            out[prop.name] = _scalar(value)

    structured = jsonld.build(repo, model_name, item)
    if structured is not None:
        out["jsonld"] = json.dumps(structured, ensure_ascii=False, separators=(",", ":"))

    return out


def _sort_key(model_name: str, item: dict[str, Any]) -> tuple:
    order = item.get("order") or ""
    published = item.get("published_at")
    published_key = published.isoformat() if isinstance(published, date) else ""
    if model_name in ("categories", "areas", "tags", "organizations"):
        return (order, item.get("name_kana") or item.get("name") or item["slug"])
    # 新しい順
    return (order, _invert(published_key), item["slug"])


def _invert(text: str) -> str:
    """文字列の昇順ソートで降順を得るための反転キー。"""
    return "".join(chr(0x10FFFF - ord(c)) if ord(c) < 0x10FFFF else c for c in text)


def list_payload(repo: Repository, model_name: str, *, limit: int = DEFAULT_LIMIT,
                 offset: int = 0, filters: dict[str, str] | None = None,
                 include_drafts: bool = False) -> dict[str, Any]:
    items = repo.model_items(model_name)
    if not include_drafts:
        items = [i for i in items if i.get("status", "公開") == "公開"]

    for key, expected in (filters or {}).items():
        items = [i for i in items if _matches(i, key, expected)]

    items.sort(key=lambda i: _sort_key(model_name, i))
    total = len(items)
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    page = items[offset:offset + limit]

    return {
        "contents": [serialize(repo, model_name, i) for i in page],
        "totalCount": total,
        "offset": offset,
        "limit": limit,
    }


def _matches(item: dict[str, Any], key: str, expected: str) -> bool:
    value = item.get(key)
    if value is None:
        return False
    if isinstance(value, list):
        return expected in [str(v) for v in value]
    return str(value) == expected


def detail_payload(repo: Repository, model_name: str, slug: str) -> dict[str, Any] | None:
    item = repo.get(model_name, slug)
    if item is None:
        return None
    return serialize(repo, model_name, item)
