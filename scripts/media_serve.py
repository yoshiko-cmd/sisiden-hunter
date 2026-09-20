#!/usr/bin/env python3
"""STUDIO Data Connect API 向けの配信サーバーを起動する。

使い方:
    python scripts/media_serve.py                      # http://127.0.0.1:8787
    python scripts/media_serve.py --host 0.0.0.0 --port 8080

STUDIO（Businessプラン以上）の API連携 で以下を登録する。
    一覧: https://<公開ホスト>/api/v1/documentaries   → 動的リストに接続
    詳細: https://<公開ホスト>/api/v1/documentaries/{slug} → 動的ページに接続

環境変数 SISIDEN_API_TOKEN を設定すると、
Authorization: Bearer <token> または X-API-KEY ヘッダーを要求する。

設計書: docs/sisiden-media/integration-toolkit.md
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.media.api.server import serve


def main() -> int:
    parser = argparse.ArgumentParser(description="SISIDEN MEDIA 配信API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
