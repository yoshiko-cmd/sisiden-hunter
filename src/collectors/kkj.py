"""官公需情報ポータルサイト 検索API コレクター。

実エンドポイント・レスポンス要素名は config/kkj_api.yaml で管理し、
本モジュールのロジックは変更不要な設計にしている(要件32のポリシーに準拠)。

このサンドボックス環境では kkj.go.jp へのアウトバウンド接続が組織の
ネットワークポリシーによりブロックされているため、fetch_live() は
その事実をそのまま例外/ログとして返す。ネットワーク到達可能な環境では
そのまま実データ取得に使える。
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


class KkjApiError(Exception):
    """kkj.go.jp APIとの通信・応答に関するエラー。"""


@dataclass
class SearchCriteria:
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
    if not date_from and not date_to:
        return None
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

    if not params:
        raise ValueError(
            "検索条件が空です。query/project_name/organization_name/lg_code の"
            "いずれか1つ以上、または日付範囲を指定してください。"
        )
    return params


def fetch_live(criteria: SearchCriteria, config: dict[str, Any] | None = None) -> str:
    """実APIへリクエストしXML文字列を返す。ネットワーク不可時はKkjApiErrorを投げる。"""
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
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "kkj API request failed (attempt %s/%s): %s",
                attempt,
                config["max_retries"],
                exc,
            )
            if attempt < config["max_retries"]:
                time.sleep(config["retry_backoff_seconds"] * attempt)

    raise KkjApiError(f"官公需情報ポータルAPIへの接続に失敗しました: {last_error}") from last_error


def fetch_fixture(fixture_path: Path) -> str:
    """テスト用フィクスチャXMLを読み込む(ネットワーク不要)。"""
    return fixture_path.read_text(encoding="utf-8")


def _text_or_none(element: ET.Element | None, tag: str) -> str | None:
    if element is None:
        return None
    child = element.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def parse_response(xml_text: str, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """レスポンスXMLをパースして案件辞書のリストを返す。"""
    config = config or load_config()
    fields = config["response_fields"]

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise KkjApiError(f"APIレスポンスのXMLパースに失敗しました: {exc}") from exc

    records: list[dict[str, Any]] = []
    for record_el in root.findall(fields["record_xpath"]):
        attachment_url_text = _text_or_none(record_el, fields["attachment_urls"])
        attachment_name_text = _text_or_none(record_el, fields["attachment_names"])
        records.append(
            {
                "source": "kkj",
                "source_key": _text_or_none(record_el, fields["source_key"]),
                "project_name": _text_or_none(record_el, fields["project_name"]),
                "organization_name": _text_or_none(record_el, fields["organization_name"]),
                "organization_type": _text_or_none(record_el, fields["organization_type"]),
                "prefecture": _text_or_none(record_el, fields["prefecture"]),
                "municipality": _text_or_none(record_el, fields["municipality"]),
                "category": _text_or_none(record_el, fields["category"]),
                "procedure_type": _text_or_none(record_el, fields["procedure_type"]),
                "published_date": _text_or_none(record_el, fields["published_date"]),
                "deadline": _text_or_none(record_el, fields["deadline"]),
                "opening_date": _text_or_none(record_el, fields["opening_date"]),
                "budget_text": _text_or_none(record_el, fields["budget_text"]),
                "external_url": _text_or_none(record_el, fields["external_url"]),
                "description": _text_or_none(record_el, fields["description"]),
                "attachment_urls": [attachment_url_text] if attachment_url_text else [],
                "attachment_names": [attachment_name_text] if attachment_name_text else [],
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
