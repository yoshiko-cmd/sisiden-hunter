"""STUDIO Data Connect API から呼ばれる配信サーバー（標準ライブラリのみ）。

エンドポイント:
  GET /api/v1/health
  GET /api/v1/{model}            一覧   → STUDIOの動的リストに接続
  GET /api/v1/{model}/{slug}     詳細   → STUDIOの動的ページに接続

クエリパラメータ:
  limit / offset                 ページング
  filters=key:value[,key:value]  絞り込み（例: filters=documentary:tonkan）
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ..content import Repository, load_repository
from . import payload

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
TOKEN_ENV = "SISIDEN_API_TOKEN"


def _parse_filters(raw: str) -> dict[str, str]:
    filters: dict[str, str] = {}
    for chunk in raw.split(","):
        if ":" in chunk:
            key, _, value = chunk.partition(":")
            key, value = key.strip(), value.strip()
            if key and value:
                filters[key] = value
    return filters


class MediaAPIHandler(BaseHTTPRequestHandler):
    server_version = "SisidenMediaAPI/1.0"
    repository: Repository

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if not path.startswith(API_PREFIX):
            self._send_json(404, {"error": "not found"})
            return

        if not self._authorized():
            self._send_json(401, {"error": "unauthorized"})
            return

        segments = [unquote(s) for s in path[len(API_PREFIX):].split("/") if s]
        query = parse_qs(parsed.query)

        if segments == ["health"]:
            self._send_json(200, {
                "status": "ok",
                "models": {
                    name: len(self.repository.items.get(name, {}))
                    for name in self.repository.schema.models
                },
            })
            return

        if not segments or segments[0] not in self.repository.schema.models:
            self._send_json(404, {"error": "unknown model"})
            return

        model_name = segments[0]

        if len(segments) == 1:
            try:
                limit = int(query.get("limit", [payload.DEFAULT_LIMIT])[0])
                offset = int(query.get("offset", ["0"])[0])
            except ValueError:
                self._send_json(400, {"error": "limit / offset must be integers"})
                return
            filters = _parse_filters(query.get("filters", [""])[0])
            self._send_json(200, payload.list_payload(
                self.repository, model_name,
                limit=limit, offset=offset, filters=filters,
            ))
            return

        if len(segments) == 2:
            body = payload.detail_payload(self.repository, model_name, segments[1])
            if body is None:
                self._send_json(404, {"error": "item not found"})
                return
            self._send_json(200, body)
            return

        self._send_json(404, {"error": "not found"})

    def _authorized(self) -> bool:
        expected = os.environ.get(TOKEN_ENV)
        if not expected:
            return True
        provided = self.headers.get("X-API-KEY") or ""
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            provided = auth[7:]
        return hmac.compare_digest(provided, expected)

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "public, max-age=60")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.info("%s - %s", self.address_string(), format % args)


def create_server(host: str = "127.0.0.1", port: int = 8787,
                  repository: Repository | None = None) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (MediaAPIHandler,), {
        "repository": repository or load_repository(),
    })
    return ThreadingHTTPServer((host, port), handler)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = create_server(host, port)
    logger.info("SISIDEN MEDIA API を起動しました: http://%s:%d%s", host, port, API_PREFIX)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
