"""CMSモデルごとにCSVを書き出す。

用途は2つ。
1. STUDIO CMS へ手入力する際の台帳（STUDIOはCSV直接インポートに非対応）
2. STUDIO にエクスポート機能がないことへの備えとしてのバックアップ台帳
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from ..content import Repository, _as_list

MULTI_VALUE_SEPARATOR = "|"


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return MULTI_VALUE_SEPARATOR.join(str(v) for v in value)
    return str(value)


def export_model(repo: Repository, model_name: str, out_dir: Path) -> Path:
    model = repo.schema.model(model_name)
    columns = [p.name for p in model.properties]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{model_name}.csv"

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([p.label for p in model.properties])
        writer.writerow(columns)
        for item in repo.model_items(model_name):
            writer.writerow([_cell(item.get(c)) for c in columns])

    return path


def export_all(repo: Repository, out_dir: Path) -> list[Path]:
    return [export_model(repo, name, out_dir) for name in repo.schema.models]


def export_redirect_map(repo: Repository, out_dir: Path, new_base: str) -> Path:
    """独立ドメイン移行用の 旧URL→新URL 対応表を書き出す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "redirects.csv"
    old_base = repo.schema.site["base_url"].rstrip("/")
    new_base = new_base.rstrip("/")

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["old_url", "new_url", "status"])
        writer.writerow([f"{old_base}/", f"{new_base}/", 301])
        for model_name, model in repo.schema.models.items():
            for slug in repo.items.get(model_name, {}):
                old = f"{old_base}/{model.path}/{slug}"
                writer.writerow([old, old.replace(old_base, new_base), 301])

    return path


def export_studio_setup_sheet(repo: Repository, out_dir: Path) -> Path:
    """STUDIO編集画面でモデルを作る際のチェックシート。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "studio_cms_setup.csv"

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "モデル", "プロパティ名", "表示ラベル", "STUDIOで選ぶタイプ",
            "参照先モデル", "選択形式", "必須", "選択肢", "設定済み",
        ])
        for model_name, model in repo.schema.models.items():
            for prop in model.properties:
                if prop.is_ref:
                    studio_type = "参照"
                    ref_target = repo.schema.model(prop.ref_target).label
                    ref_mode = "マルチセレクト" if prop.is_multi_ref else "シングルセレクト"
                else:
                    studio_type = {
                        "text": "テキスト",
                        "textarea": "テキスト（複数行）",
                        "richtext": "リッチテキスト",
                        "image": "画像",
                        "date": "日付",
                        "select": "セレクト",
                        "multiselect": "マルチセレクト",
                        "slug": "スラッグ",
                    }.get(prop.type, prop.type)
                    ref_target = ""
                    ref_mode = ""
                writer.writerow([
                    model.label, prop.name, prop.label, studio_type,
                    ref_target, ref_mode, "●" if prop.required else "",
                    " / ".join(prop.options), "",
                ])

    return path
