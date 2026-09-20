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

import requests
import yaml

logger = logging.getLogger("sisiden.collectors.kkj")

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "config" / "kkj_api.yaml"

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
    lg_code: str | None = None
    published_from: str | None = None
    published_to: str | None = None
    deadline_from: str | None = None
    deadline_to: str | None = None


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    with open(config_path, encoding="utf-8") as f:
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
    if criteria.lg_code:
        params[p["lg_code_param"]] = criteria.lg_code

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
                "project_name": _text(record_el, fields["project_name"]),
                "organization_name": organization_name,
                "organization_type": infer_organization_type(organization_name, prefecture, municipality),
                "prefecture": prefecture,
                "municipality": municipality,
                "category": _text(record_el, fields["category"]),
                "procedure_type": _text(record_el, fields["procedure_type"]),
                "published_date": _text(record_el, fields["published_date"]),
                "deadline": _text(record_el, fields["deadline"]),
                "opening_date": _text(record_el, fields["opening_date"]),
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


def collect_multi(
    queries: list[str],
    *,
    published_from: str | None = None,
    published_to: str | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """複数キーワードで全国横断収集する。

    APIはLG_Code未指定時に全国を対象とするため、キーワードを変えて複数回呼び出す。
    1つのキーワードが失敗しても他を継続する(要件34)。

    戻り値: (案件リスト(Keyで重複除去済み), エラーメッセージのリスト)
    """
    config = config or load_config()
    interval = config.get("request_interval_seconds", 1.0)

    collected: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(interval)
        criteria = SearchCriteria(
            query=query, published_from=published_from, published_to=published_to
        )
        try:
            records = collect(criteria, live=True, config=config)
        except (KkjApiError, ValueError) as exc:
            logger.error("キーワード '%s' の収集に失敗しました: %s", query, exc)
            errors.append(f"{query}: {exc}")
            continue

        logger.info("キーワード '%s': %d件", query, len(records))
        for record in records:
            key = record.get("source_key") or f"{record.get('project_name')}|{record.get('external_url')}"
            collected.setdefault(key, record)

    return list(collected.values()), errors
