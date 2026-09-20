#!/usr/bin/env python3
"""DBファイルを初期化する (schema.sqlを適用)。既存テーブルは変更しない。"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "sisiden_opportunities.db"
SCHEMA_PATH = ROOT / "src" / "database" / "schema.sql"


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
    print(f"DB initialized: {db_path}")


if __name__ == "__main__":
    init_db()
    sys.exit(0)
