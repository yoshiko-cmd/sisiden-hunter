"""添付PDFからのテキスト抽出(pypdfによるローカル処理)。

LLM APIは一切使用しない。抽出したテキストはローカルに保存し、
再スコアリングとMCPツール get_specification_text から利用する。

画像スキャンのみのPDFはテキストが取れない。その場合は「取れなかった」ことを
正直にstatusとして記録する(勝手にOCRや外部サービスへ送信しない)。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger("sisiden.attachments.extractor")

ROOT = Path(__file__).resolve().parent.parent.parent
ATTACHMENTS_DIR = ROOT / "data" / "attachments"

# 1案件あたりの抽出テキスト上限(異常に巨大なPDF対策)
MAX_TOTAL_CHARS = 2_000_000


@dataclass
class ExtractedDocument:
    """1ファイル分の抽出結果。"""

    file_name: str
    source_path: str
    pages: list[str] = field(default_factory=list)
    status: str = "extracted"  # extracted / empty / failed / unsupported
    note: str | None = None

    @property
    def char_count(self) -> int:
        return sum(len(p) for p in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "source_path": self.source_path,
            "status": self.status,
            "note": self.note,
            "page_count": self.page_count,
            "char_count": self.char_count,
            "pages": self.pages,
        }


def detect_file_type(path: Path) -> str:
    """ファイルの中身から種別を判定する。

    官公需APIの添付ファイル名は「通常はリンク文字列」(APIガイド4.2)であり、
    「入札公告」「仕様書」のように拡張子を持たない。拡張子で判定すると
    すべてPDF以外とみなされてしまうため、先頭バイトで判定する。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(512)
    except OSError:
        return "unreadable"

    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip"  # docx/xlsx/zip
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"  # 旧Office形式 (doc/xls)
    lowered = head.lstrip().lower()
    if lowered.startswith((b"<!doctype html", b"<html", b"<?xml")):
        return "html"
    return "unknown"


def extract_pdf_text(pdf_path: Path) -> ExtractedDocument:
    """PDFからページ単位でテキストを抽出する。失敗しても例外を投げない。"""
    doc = ExtractedDocument(file_name=pdf_path.name, source_path=str(pdf_path))

    file_type = detect_file_type(pdf_path)
    if file_type != "pdf":
        doc.status = "unsupported"
        doc.note = {
            "html": "PDFではなくHTMLページでした(添付URLが案内ページを指している可能性)",
            "zip": "PDFではなくZIP/Office形式(docx等)のファイルでした",
            "ole": "PDFではなく旧Office形式(doc/xls)のファイルでした",
            "unreadable": "ファイルを読み取れませんでした",
        }.get(file_type, "PDF形式ではないファイルでした")
        return doc

    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            # 空パスワードで開ける場合があるため一度試す
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001 - 暗号化方式は多様で、失敗しても処理を続ける
                doc.status = "failed"
                doc.note = "暗号化されたPDFのため読み取れません"
                return doc

        total = 0
        for page in reader.pages:
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001 - 1ページの失敗で全体を止めない
                logger.warning("ページ抽出に失敗しました (%s): %s", pdf_path.name, exc)
                text = ""
            total += len(text)
            if total > MAX_TOTAL_CHARS:
                doc.note = "テキスト量が上限に達したため以降を打ち切りました"
                break
            doc.pages.append(text)

        if doc.char_count == 0:
            doc.status = "empty"
            doc.note = doc.note or "テキストが埋め込まれていません(画像スキャンPDFの可能性)"
    except PdfReadError as exc:
        doc.status = "failed"
        doc.note = f"PDFの解析に失敗しました: {exc}"
    except OSError as exc:
        doc.status = "failed"
        doc.note = f"ファイルの読み込みに失敗しました: {exc}"

    return doc


def extracted_dir(opportunity_id: int, base_dir: Path = ATTACHMENTS_DIR) -> Path:
    return base_dir / f"opportunity_{opportunity_id}" / "extracted"


def cache_path(opportunity_id: int, base_dir: Path = ATTACHMENTS_DIR) -> Path:
    return extracted_dir(opportunity_id, base_dir) / "documents.json"


def save_extraction(
    opportunity_id: int, documents: list[ExtractedDocument], base_dir: Path = ATTACHMENTS_DIR
) -> Path:
    """抽出結果をJSONで保存する(再抽出を避けるためのキャッシュ)。"""
    out_dir = extracted_dir(opportunity_id, base_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = cache_path(opportunity_id, base_dir)
    payload = {"opportunity_id": opportunity_id, "documents": [d.to_dict() for d in documents]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_extraction(opportunity_id: int, base_dir: Path = ATTACHMENTS_DIR) -> list[dict] | None:
    """保存済みの抽出結果を読み込む。未抽出ならNone。"""
    path = cache_path(opportunity_id, base_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))["documents"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        logger.warning("抽出結果の読み込みに失敗しました (id=%s): %s", opportunity_id, exc)
        return None


def combined_text(documents: list[dict]) -> str:
    """再スコアリング用に全ドキュメントのテキストを結合する。"""
    parts: list[str] = []
    for doc in documents:
        parts.extend(doc.get("pages") or [])
    return "\n".join(parts)
