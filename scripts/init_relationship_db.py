#!/usr/bin/env python3
"""Relationship OS のDBファイルを初期化する(schema.sqlを適用)。既存テーブルは変更しない。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.relationship.database.db import DEFAULT_DB_PATH, init_db


if __name__ == "__main__":
    init_db(DEFAULT_DB_PATH)
    print(f"Relationship OS DB initialized: {DEFAULT_DB_PATH}")
    sys.exit(0)
