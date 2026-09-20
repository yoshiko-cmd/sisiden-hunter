#!/usr/bin/env python3
"""SISIDEN MEDIA の正本データを検証し、Knowledge Graphの状態を出力する。

使い方:
    python scripts/media_validate.py            # 検証 + グラフ集計
    python scripts/media_validate.py --stats    # グラフ集計のみ
    python scripts/media_validate.py --strict   # WARNもエラー終了扱いにする

設計書: docs/sisiden-media/02-information-architecture.md（2-7 回遊の質を測る指標）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.media.content import ERROR, WARN, format_issues, graph_stats, load_repository, validate


def print_stats(stats: dict) -> None:
    print("── コンテンツ件数 ─────────────────────")
    for model, count in stats["counts"].items():
        print(f"  {model:<16} {count:>5}")
    print()
    print("── Knowledge Graph ───────────────────")
    print(f"  ノード数            {stats['nodes']:>5}")
    print(f"  エッジ数            {stats['edges']:>5}")
    print(f"  ノードあたり接続数    {stats['edges_per_node']:>5}   （目標 4.0以上）")
    print(f"  孤立ノード率         {stats['isolated_rate']:>5}   （目標 0.1未満）")
    print(f"  1作品あたり記事数     {stats['articles_per_documentary']:>5}   （目標 3.0以上）")
    if stats["isolated_nodes"]:
        print()
        print("  接続が不足しているノード:")
        for node in stats["isolated_nodes"]:
            print(f"    - {node}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="SISIDEN MEDIA 正本データの検証")
    parser.add_argument("--stats", action="store_true", help="グラフ集計のみ表示する")
    parser.add_argument("--strict", action="store_true", help="WARNもエラー終了扱いにする")
    args = parser.parse_args()

    repo = load_repository()
    stats = graph_stats(repo)

    if args.stats:
        print_stats(stats)
        return 0

    issues = validate(repo)
    print(format_issues(issues))
    print()
    print_stats(stats)

    errors = [i for i in issues if i.level == ERROR]
    warns = [i for i in issues if i.level == WARN]
    if errors:
        return 1
    if args.strict and warns:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
