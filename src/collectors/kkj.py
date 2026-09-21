"""官公需情報ポータルサイト 検索API コレクター。

公式APIガイド V1.1 (https://www.kkj.go.jp/doc/ja/api_guide.pdf) に準拠。
エンドポイント・タグ名は config/kkj_api.yaml で管理し、仕様変更時は
設定ファイルのみの修正で追従できるようにしている。
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests
import yaml

logger = logging.getLogger("sisiden.collectors.kkj")

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "config" / "kkj_api.yaml"
QUERIES_PATH = ROOT / "config" / "collection_queries.yaml"

# 発注機関タイプ判定用(要件4: 発注機関タイプをDB上で判別可能にする)
_NATIONAL_ORG_HINTS = ("省", "庁", "内閣", "裁判所", "会計検査院", "人事院")
_INDEPENDENT_ORG_HINTS = ("独立行政法人", "国立研究開発法人", "国立大学法人", "機構", "公社", "事業団", "公団")
_PUBLIC_ORG_HINTS = ("一般社団法人", "公益社団法人", "一般財団法人", "公益財団法人", "組合", "広域連合", "事務組合")


class KkjApiError(Exception):
    """kkj.go.jp APIとの通信・応答に関するエラー。"""


@dataclass
class SearchCriteria:
    """検索条件。Query/Project_Name/Organization_Name/LG_Code のいずれか1つ以上が必須。"""

    query: str | None = None
    project_name: str | None = None
    organization_name: str | None = None
    lg_codes: list[str] | None = None       # 都道府県コード(複数可、カンマ区切りで送信)
    certifications: list[str] | None = None  # 入札資格 A/B/C/D(複数可)
    count: int | None = None                 # 未指定時はconfigのdefault_countを使う
    published_from: str | None = None
    published_to: str | None = None
    deadline_from: str | None = None
    deadline_to: str | None = None


def build_or_query(words: list[str]) -> str:
    """キーワード群をOR検索式に変換する(APIガイド3.1)。

    演算子の前後には半角空白が必要。空白を含む語は()で囲んで優先順位を明示する。
    """
    terms = []
    for word in words:
        word = word.strip()
        if not word:
            continue
        terms.append(f"({word})" if " " in word else word)
    return " OR ".join(terms)


def build_tier_queries(tier: dict[str, Any]) -> list[str]:
    """収集階層の定義から検索式のリストを組み立てる。

    standalone: (語1 OR 語2 ...)
    combined:   (語1 OR 語2 ...) AND (修飾語1 OR 修飾語2 ...)

    演算子の優先順位はNOT > AND/OR/ANDNOT(左から評価)のため、
    combinedでは必ず括弧で優先順位を明示する(APIガイド3.1)。
    """
    words = [w for w in tier.get("words", []) if w and w.strip()]
    if not words:
        return []

    chunk_size = tier.get("chunk_size", 8)
    chunks = [words[i : i + chunk_size] for i in range(0, len(words), chunk_size)]

    if tier.get("mode") == "combined":
        modifiers = [m for m in tier.get("modifiers", []) if m and m.strip()]
        if not modifiers:
            raise ValueError("mode: combined の階層には modifiers が必要です")
        modifier_expr = build_or_query(modifiers)
        return [f"({build_or_query(chunk)}) AND ({modifier_expr})" for chunk in chunks]

    return [build_or_query(chunk) for chunk in chunks]


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_collection_queries(path: Path = QUERIES_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _date_range_param(date_from: str | None, date_to: str | None) -> str | None:
    """APIガイド3.2の期間形式に変換する。"""
    if not date_from and not date_to:
        return None
    if date_from and date_to and date_from == date_to:
        return date_from  # 「開始終了日」形式
    return f"{date_from or ''}/{date_to or ''}"


def build_request_params(criteria: SearchCriteria, config: dict[str, Any]) -> dict[str, str]:
    p = config["request_params"]
    params: dict[str, str] = {}
    if criteria.query:
        params[p["query_param"]] = criteria.query
    if criteria.project_name:
        params[p["project_name_param"]] = criteria.project_name
    if criteria.organization_name:
        params[p["organization_name_param"]] = criteria.organization_name
    if criteria.lg_codes:
        params[p["lg_code_param"]] = ",".join(criteria.lg_codes)
    if criteria.certifications:
        params[p["certification_param"]] = ",".join(criteria.certifications)

    # Countは未指定だとデフォルト10件しか返らないため必ず指定する(APIガイド3章)
    count = criteria.count or config["default_count"]
    params[p["count_param"]] = str(min(int(count), config["max_count"]))

    published_range = _date_range_param(criteria.published_from, criteria.published_to)
    if published_range:
        params[p["cft_issue_date_param"]] = published_range

    deadline_range = _date_range_param(criteria.deadline_from, criteria.deadline_to)
    if deadline_range:
        params[p["tender_submission_deadline_param"]] = deadline_range

    required = {p["query_param"], p["project_name_param"], p["organization_name_param"], p["lg_code_param"]}
    if not required & params.keys():
        raise ValueError(
            "Query / Project_Name / Organization_Name / LG_Code のいずれか1つ以上の指定が必須です"
        )
    return params


def fetch_live(criteria: SearchCriteria, config: dict[str, Any] | None = None) -> str:
    """実APIへリクエストしXML文字列を返す。失敗時はKkjApiErrorを投げる。"""
    config = config or load_config()
    params = build_request_params(criteria, config)
    last_error: Exception | None = None

    for attempt in range(1, config["max_retries"] + 1):
        try:
            resp = requests.get(
                config["endpoint"],
                params=params,
                timeout=config["timeout_seconds"],
            )
            resp.raise_for_status()
            # APIはXML宣言でエンコーディングを示すため、bytesのままパーサーに渡せるよう文字列化を調整
            resp.encoding = resp.encoding or "utf-8"
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "kkj API request failed (attempt %s/%s): %s", attempt, config["max_retries"], exc
            )
            if attempt < config["max_retries"]:
                time.sleep(config["retry_backoff_seconds"] * attempt)

    raise KkjApiError(f"官公需情報ポータルAPIへの接続に失敗しました: {last_error}") from last_error


def fetch_fixture(fixture_path: Path) -> str:
    """テスト用フィクスチャXMLを読み込む(ネットワーク不要)。"""
    return fixture_path.read_text(encoding="utf-8")


def decode_project_name(name: str | None) -> str | None:
    """案件名がURLエンコードされている場合にデコードする。

    実データに「%E2%96%B62026.09.07_Science%20Tokyo%E8%AA%8D」のように、
    ファイル名をURLエンコードしたまま案件名に入れている発注機関がある。
    デコードしないとキーワード判定が一切効かない。
    """
    if not name or "%" not in name:
        return name
    try:
        decoded = unquote(name)
    except (UnicodeDecodeError, ValueError):
        return name
    # デコードで文字化けした場合(元がURLエンコードでなかった場合)は元の値を使う
    return decoded if decoded.isprintable() else name


def _text(element: ET.Element, tag: str) -> str | None:
    """子要素のテキストを取得する。オプション項目はタグ自体が存在しないことがある(4.2)。"""
    child = element.find(tag)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def infer_organization_type(
    organization_name: str | None, prefecture: str | None, municipality: str | None
) -> str | None:
    """発注機関タイプを推定する。APIに専用タグが無いため、機関名と地域コードから判定する。"""
    name = organization_name or ""
    if any(hint in name for hint in _INDEPENDENT_ORG_HINTS):
        return "独立行政法人等"
    if any(hint in name for hint in _PUBLIC_ORG_HINTS):
        return "公的機関"
    if municipality:
        return "市区町村"
    if any(hint in name for hint in _NATIONAL_ORG_HINTS):
        return "国"
    if prefecture:
        return "都道府県"
    return None


def _parse_attachments(record_el: ET.Element, fields: dict[str, str]) -> tuple[list[str], list[str]]:
    """<Attachments><Attachment><Name>/<Uri> の入れ子構造から添付情報を抽出する(4.1)。"""
    urls: list[str] = []
    names: list[str] = []
    container = record_el.find(fields["attachments_container"])
    if container is None:
        return urls, names

    for attachment in container.findall(fields["attachment_item"]):
        uri = _text(attachment, fields["attachment_uri"])
        if not uri:
            continue
        urls.append(uri)
        names.append(_text(attachment, fields["attachment_name"]) or "")
    return urls, names


def parse_response(xml_text: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """レスポンスXMLをパースして案件辞書のリストを返す。

    エラー応答(<Results><Error>...</Error></Results>)の場合はKkjApiErrorを投げる(5章)。
    """
    config = config or load_config()
    fields = config["response_fields"]

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise KkjApiError(f"APIレスポンスのXMLパースに失敗しました: {exc}") from exc

    error_el = root.find(fields["error_xpath"])
    if error_el is not None and error_el.text:
        raise KkjApiError(f"APIがエラーを返しました: {error_el.text.strip()}")

    records: list[dict[str, Any]] = []
    for record_el in root.findall(fields["record_xpath"]):
        attachment_urls, attachment_names = _parse_attachments(record_el, fields)
        prefecture = _text(record_el, fields["prefecture"])
        municipality = _text(record_el, fields["municipality"])
        organization_name = _text(record_el, fields["organization_name"])

        records.append(
            {
                "source": "kkj",
                "source_key": _text(record_el, fields["source_key"]),
                "project_name": decode_project_name(_text(record_el, fields["project_name"])),
                "organization_name": organization_name,
                "organization_type": infer_organization_type(organization_name, prefecture, municipality),
                "prefecture": prefecture,
                "municipality": municipality,
                "category": _text(record_el, fields["category"]),
                "procedure_type": _text(record_el, fields["procedure_type"]),
                "published_date": _text(record_el, fields["published_date"]),
                # TenderSubmissionDeadlineはタグ名に反しAPIガイド上「入札開始日」とされる。
                # 応募締切と決めつけず、API由来の生値として保持する。
                "api_tender_date": _text(record_el, fields["api_tender_date"]),
                "opening_date": _text(record_el, fields["opening_date"]),
                "period_end_time": _text(record_el, fields["period_end_time"]),
                "budget_text": None,  # このAPIは予定価格を返さない(添付の公告文に記載)
                "external_url": _text(record_el, fields["external_url"]),
                "description": _text(record_el, fields["description"]),
                "location": _text(record_el, fields["location"]),
                "certification": _text(record_el, fields["certification"]),
                "attachment_urls": attachment_urls,
                "attachment_names": attachment_names,
            }
        )
    return records


def collect(
    criteria: SearchCriteria | None = None,
    *,
    live: bool = True,
    fixture_path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """案件を収集する。live=Falseの場合はfixture_pathからXMLを読み込む(テスト用)。"""
    config = config or load_config()
    if live:
        xml_text = fetch_live(criteria or SearchCriteria(), config)
    else:
        if fixture_path is None:
            raise ValueError("live=Falseの場合はfixture_pathが必要です")
        xml_text = fetch_fixture(fixture_path)
    return parse_response(xml_text, config)


def _record_key(record: dict[str, Any]) -> str:
    return record.get("source_key") or f"{record.get('project_name')}|{record.get('external_url')}"


def collect_queries(
    queries: list[str],
    *,
    published_from: str | None = None,
    published_to: str | None = None,
    lg_codes: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """検索式のリストを順に実行し、結果をKeyで重複除去して返す。

    LG_Code未指定時は全国が対象。1つの検索式が失敗しても他は継続する(要件34)。

    戻り値: (案件リスト(重複除去済み), エラーメッセージのリスト)
    """
    config = config or load_config()
    interval = config.get("request_interval_seconds", 1.0)

    collected: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(interval)
        criteria = SearchCriteria(
            query=query,
            published_from=published_from,
            published_to=published_to,
            lg_codes=lg_codes,
        )
        try:
            records = collect(criteria, live=True, config=config)
        except (KkjApiError, ValueError) as exc:
            logger.error("検索式 '%s' の収集に失敗しました: %s", query, exc)
            errors.append(f"{query}: {exc}")
            continue

        logger.info("検索式 '%s': %d件", query[:60], len(records))
        if len(records) >= config["max_count"]:
            logger.warning(
                "取得件数が上限(%d件)に達しました。期間や都道府県で絞り込むと取りこぼしを防げます。",
                config["max_count"],
            )
        for record in records:
            collected.setdefault(_record_key(record), record)

    return list(collected.values()), errors


def collect_multi(
    keywords: list[str],
    *,
    published_from: str | None = None,
    published_to: str | None = None,
    lg_codes: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """キーワード群をOR検索式にまとめて収集する(URL長に配慮して分割)。"""
    config = config or load_config()
    chunk_size = config.get("or_query_chunk_size", 10)
    chunks = [keywords[i : i + chunk_size] for i in range(0, len(keywords), chunk_size)]
    queries = [build_or_query(chunk) for chunk in chunks]
    return collect_queries(
        queries,
        published_from=published_from,
        published_to=published_to,
        lg_codes=lg_codes,
        config=config,
    )


def collect_tiers(
    *,
    published_from: str | None = None,
    published_to: str | None = None,
    lg_codes: list[str] | None = None,
    tiers: list[str] | None = None,
    config: dict[str, Any] | None = None,
    queries_config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, int]]:
    """3階層(Priority A/B/C)で収集し、階層をまたいで重複除去する。

    案件名に「映像」「動画」と書かれていなくても物語にできる案件を拾うため、
    映像系(A)・広報発信系(B)・テーマ系(C: 発信語とAND結合)の3階層で網を張る。

    戻り値: (案件リスト(重複除去済み), エラーリスト, 階層ごとの新規件数)
    """
    config = config or load_config()
    queries_config = queries_config or load_collection_queries()

    collected: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    tier_stats: dict[str, int] = {}

    target_tiers = tiers or list(queries_config["tiers"].keys())

    for tier_name in target_tiers:
        tier = queries_config["tiers"].get(tier_name)
        if tier is None:
            errors.append(f"階層 '{tier_name}' の定義が見つかりません")
            continue

        tier_queries = build_tier_queries(tier)
        logger.info("Priority %s (%s): 検索式%d件", tier_name, tier.get("label", ""), len(tier_queries))

        records, tier_errors = collect_queries(
            tier_queries,
            published_from=published_from,
            published_to=published_to,
            lg_codes=lg_codes,
            config=config,
        )
        errors.extend(f"[{tier_name}] {e}" for e in tier_errors)

        before = len(collected)
        for record in records:
            collected.setdefault(_record_key(record), record)
        tier_stats[tier_name] = len(collected) - before
        logger.info(
            "Priority %s: 取得%d件 うち新規%d件(階層間の重複を除外)",
            tier_name,
            len(records),
            tier_stats[tier_name],
        )

    return list(collected.values()), errors, tier_stats


def collect_by_prefecture(
    *,
    published_from: str | None = None,
    published_to: str | None = None,
    tiers: list[str] | None = None,
    config: dict[str, Any] | None = None,
    queries_config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """47都道府県を1つずつ、3階層で収集する(1リクエスト1,000件の上限対策)。

    全国一括では上限に達する恐れがある場合に使う。
    """
    config = config or load_config()
    queries_config = queries_config or load_collection_queries()
    interval = config.get("request_interval_seconds", 1.0)

    collected: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for i, (code, name) in enumerate(sorted(config["prefecture_codes"].items())):
        if i > 0:
            time.sleep(interval)
        records, chunk_errors, _ = collect_tiers(
            published_from=published_from,
            published_to=published_to,
            lg_codes=[code],
            tiers=tiers,
            config=config,
            queries_config=queries_config,
        )
        errors.extend(f"{name}: {e}" for e in chunk_errors)
        logger.info("%s (%s): %d件", name, code, len(records))
        for record in records:
            collected.setdefault(_record_key(record), record)

    return list(collected.values()), errors
