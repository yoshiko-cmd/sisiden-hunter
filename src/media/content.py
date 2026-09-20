"""content/ 配下のYAMLを正本として読み込み、検証とグラフ集計を行う。"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import yaml

from .schema import CONTENT_DIR, Model, Schema, load_schema

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

ERROR = "ERROR"
WARN = "WARN"


@dataclass(frozen=True)
class Issue:
    level: str
    model: str
    slug: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.model}/{self.slug}: {self.message}"


@dataclass
class Repository:
    schema: Schema
    items: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def model_items(self, model_name: str) -> list[dict[str, Any]]:
        return list(self.items.get(model_name, {}).values())

    def published(self, model_name: str) -> list[dict[str, Any]]:
        return [i for i in self.model_items(model_name) if i.get("status", "公開") == "公開"]

    def get(self, model_name: str, slug: str) -> dict[str, Any] | None:
        return self.items.get(model_name, {}).get(slug)

    def url_for(self, model_name: str, slug: str) -> str:
        return self.schema.url_for(model_name, slug)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def load_repository(content_dir: Path = CONTENT_DIR, schema: Schema | None = None) -> Repository:
    schema = schema or load_schema()
    repo = Repository(schema=schema)

    for model_name in schema.models:
        repo.items[model_name] = {}
        model_dir = content_dir / model_name
        if not model_dir.is_dir():
            continue
        for path in sorted(model_dir.glob("*.yaml")):
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            data.setdefault("slug", path.stem)
            data["_source"] = str(path.relative_to(content_dir.parent))
            repo.items[model_name][data["slug"]] = data

    return repo


def validate(repo: Repository) -> list[Issue]:
    issues: list[Issue] = []
    schema = repo.schema
    rules = schema.validation

    for model_name, model in schema.models.items():
        for slug, item in repo.items.get(model_name, {}).items():
            issues.extend(_validate_item(repo, model, slug, item))

    if rules.get("require_documentary_on_article", True):
        for slug, item in repo.items.get("articles", {}).items():
            if not item.get("documentary"):
                issues.append(
                    Issue(ERROR, "articles", slug,
                          "documentary が未設定です。所属作品のない記事は作らない方針です")
                )

    if rules.get("require_consent_for_published_people", True):
        for slug, item in repo.items.get("people", {}).items():
            if item.get("status") == "公開" and item.get("consent_status") != "取得済":
                issues.append(
                    Issue(ERROR, "people", slug,
                          "consent_status が「取得済」ではないため公開できません")
                )

    issues.extend(_validate_graph(repo))
    return issues


def _validate_item(repo: Repository, model: Model, slug: str, item: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []

    if not SLUG_RE.match(slug):
        issues.append(Issue(ERROR, model.name, slug,
                            "slugは英小文字・数字・ハイフンのみで構成してください"))

    known = {p.name for p in model.properties} | {"slug", "_source"}
    for key in item:
        if key not in known:
            issues.append(Issue(WARN, model.name, slug, f"未定義のプロパティです: {key}"))

    for prop in model.properties:
        value = item.get(prop.name)
        empty = value is None or (isinstance(value, (str, list)) and len(value) == 0)

        if prop.required and empty:
            issues.append(Issue(ERROR, model.name, slug,
                                f"必須プロパティが未入力です: {prop.name}（{prop.label}）"))
            continue
        if empty:
            continue

        if prop.options and value not in prop.options:
            issues.append(Issue(ERROR, model.name, slug,
                                f"{prop.name} の値 '{value}' は選択肢にありません: "
                                f"{', '.join(prop.options)}"))

        if prop.type == "date" and not isinstance(value, date):
            issues.append(Issue(ERROR, model.name, slug,
                                f"{prop.name} は日付形式（YYYY-MM-DD）で記述してください"))

        if prop.is_ref:
            target = prop.ref_target
            refs = _as_list(value)
            if prop.is_single_ref and len(refs) > 1:
                issues.append(Issue(ERROR, model.name, slug,
                                    f"{prop.name} は単一参照です。複数指定されています"))
            for ref_slug in refs:
                if repo.get(target, ref_slug) is None:
                    issues.append(Issue(ERROR, model.name, slug,
                                        f"{prop.name} の参照先が存在しません: "
                                        f"{target}/{ref_slug}"))

    return issues


def _validate_graph(repo: Repository) -> list[Issue]:
    issues: list[Issue] = []
    min_edges = repo.schema.validation.get("min_edges_per_node", 2)
    degree = edge_degrees(repo)

    for model_name in ("documentaries", "people", "issues", "areas"):
        for slug in repo.items.get(model_name, {}):
            if degree[(model_name, slug)] < min_edges:
                issues.append(
                    Issue(WARN, model_name, slug,
                          f"接続数が{degree[(model_name, slug)]}件しかありません"
                          f"（目安{min_edges}件以上）。回遊の行き止まりになります")
                )

    target = repo.schema.validation.get("target_articles_per_documentary", 3)
    counts = defaultdict(int)
    for item in repo.model_items("articles"):
        if item.get("documentary"):
            counts[item["documentary"]] += 1
    for slug in repo.items.get("documentaries", {}):
        if counts[slug] < target:
            issues.append(
                Issue(WARN, "documentaries", slug,
                      f"紐づく記事が{counts[slug]}本です（目安{target}本以上）")
            )

    return issues


def edge_degrees(repo: Repository) -> dict[tuple[str, str], int]:
    """各ノードの接続数（双方向にカウント）を返す。"""
    degree: dict[tuple[str, str], int] = defaultdict(int)
    for model_name, model in repo.schema.models.items():
        for slug, item in repo.items.get(model_name, {}).items():
            degree[(model_name, slug)] += 0
            for prop in model.ref_properties:
                for ref_slug in _as_list(item.get(prop.name)):
                    if repo.get(prop.ref_target, ref_slug) is None:
                        continue
                    degree[(model_name, slug)] += 1
                    degree[(prop.ref_target, ref_slug)] += 1
    return degree


def graph_stats(repo: Repository) -> dict[str, Any]:
    degree = edge_degrees(repo)
    node_models = ("documentaries", "people", "issues", "areas")
    nodes = sum(len(repo.items.get(m, {})) for m in node_models)
    edges = sum(degree.values()) // 2
    min_edges = repo.schema.validation.get("min_edges_per_node", 2)
    isolated = [
        f"{m}/{s}"
        for m in node_models
        for s in repo.items.get(m, {})
        if degree[(m, s)] < min_edges
    ]
    documentaries = len(repo.items.get("documentaries", {}))
    articles = len(repo.items.get("articles", {}))

    return {
        "counts": {m: len(repo.items.get(m, {})) for m in repo.schema.models},
        "nodes": nodes,
        "edges": edges,
        "edges_per_node": round(edges / nodes, 2) if nodes else 0.0,
        "isolated_nodes": isolated,
        "isolated_rate": round(len(isolated) / nodes, 3) if nodes else 0.0,
        "articles_per_documentary": round(articles / documentaries, 2) if documentaries else 0.0,
    }


def format_issues(issues: Iterable[Issue]) -> str:
    issues = list(issues)
    if not issues:
        return "問題は見つかりませんでした。"
    errors = [i for i in issues if i.level == ERROR]
    warns = [i for i in issues if i.level == WARN]
    lines = [str(i) for i in errors] + [str(i) for i in warns]
    lines.append("")
    lines.append(f"ERROR {len(errors)}件 / WARN {len(warns)}件")
    return "\n".join(lines)
