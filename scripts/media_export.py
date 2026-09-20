#!/usr/bin/env python3
"""正本データをSTUDIOに取り込める形式へ書き出す。

使い方:
    python scripts/media_export.py --format csv        # モデルごとのCSV台帳
    python scripts/media_export.py --format setup      # STUDIO CMS設定チェックシート
    python scripts/media_export.py --format wxr        # 記事の一括インポート用WordPress XML
    python scripts/media_export.py --format jsonld     # ページごとのJSON-LD
    python scripts/media_export.py --format redirects --new-base https://sisiden.jp
    python scripts/media_export.py --format all

出力先は data/media_export/（--out で変更可）。

設計書: docs/sisiden-media/integration-toolkit.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.media import jsonld
from src.media.content import load_repository
from src.media.exporters import csv_export, wxr

DEFAULT_OUT = ROOT / "data" / "media_export"


def export_jsonld(repo, out_dir: Path) -> list[Path]:
    out_dir = out_dir / "jsonld"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    site_path = out_dir / "_site.json"
    site_path.write_text(
        json.dumps(
            {"organization": jsonld.organization(repo), "website": jsonld.website(repo)},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    written.append(site_path)

    for model_name in jsonld.BUILDERS:
        model_dir = out_dir / model_name
        model_dir.mkdir(exist_ok=True)
        for item in repo.model_items(model_name):
            built = jsonld.build(repo, model_name, item)
            path = model_dir / f"{item['slug']}.json"
            path.write_text(json.dumps(built, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="SISIDEN MEDIA のエクスポート")
    parser.add_argument(
        "--format", required=True,
        choices=["csv", "setup", "wxr", "jsonld", "redirects", "all"],
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--new-base", default="https://sisiden.jp",
                        help="redirects で使う移行先のベースURL")
    args = parser.parse_args()

    repo = load_repository()
    out_dir: Path = args.out
    written: list[Path] = []

    if args.format in ("csv", "all"):
        written += csv_export.export_all(repo, out_dir / "csv")
    if args.format in ("setup", "all"):
        written.append(csv_export.export_studio_setup_sheet(repo, out_dir))
    if args.format in ("wxr", "all"):
        written.append(wxr.export_articles(repo, out_dir))
    if args.format in ("jsonld", "all"):
        written += export_jsonld(repo, out_dir)
    if args.format in ("redirects", "all"):
        written.append(csv_export.export_redirect_map(repo, out_dir, args.new_base))

    for path in written:
        print(path.relative_to(ROOT))
    print(f"\n{len(written)}ファイルを書き出しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
