"""添付資料(仕様書PDF等)のダウンロード(要件13,34,35)。

- ファイル名はサニタイズし、そのままファイルシステムパスとして使わない。
- タイムアウト、HTTPエラー、巨大ファイルに対応する。
- 任意コードは実行しない。ダウンロードのみ行う。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger("sisiden.attachments")

ROOT = Path(__file__).resolve().parent.parent.parent
ATTACHMENTS_DIR = ROOT / "data" / "attachments"

MAX_FILE_SIZE_BYTES = 30 * 1024 * 1024  # 30MB
REQUEST_TIMEOUT_SECONDS = 20
ALLOWED_SCHEMES = {"http", "https"}


@dataclass
class DownloadResult:
    url: str
    success: bool
    local_path: str | None = None
    error: str | None = None


def sanitize_filename(name: str, fallback: str = "attachment") -> str:
    """ファイル名をファイルシステムパスとして安全な形にサニタイズする(要件35)。"""
    name = (name or "").strip()
    if not name:
        name = fallback
    name = Path(name).name  # ディレクトリトラバーサル対策 (../ 等を除去)
    name = re.sub(r"[^\w\-.぀-ヿ一-鿿]", "_", name)
    name = name.strip("._") or fallback
    return name[:200]


def _filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    return sanitize_filename(Path(parsed.path).name or "attachment")


# Content-Type から拡張子を決めるための対応表
_CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/x-pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/zip": ".zip",
    "text/html": ".html",
}


def resolve_filename(url: str, link_text: str | None, content_type: str | None = None) -> str:
    """保存するファイル名を決める。

    官公需APIの添付ファイル名は「通常はリンク文字列」(APIガイド4.2)であり、
    「入札公告」「仕様書」のように拡張子を持たない。リンク文字列をそのまま
    ファイル名にすると拡張子が失われるため、URL または Content-Type から
    拡張子を補う。
    """
    url_name = _filename_from_url(url)
    extension = Path(url_name).suffix.lower()

    if not extension and content_type:
        base_type = content_type.split(";")[0].strip().lower()
        extension = _CONTENT_TYPE_EXTENSIONS.get(base_type, "")

    # リンク文字列があれば人が読める名前として使い、拡張子だけ補う
    base = sanitize_filename(link_text) if link_text else Path(url_name).stem
    base = Path(base).stem or "attachment"
    return f"{base}{extension}" if extension else base


def download_attachment(url: str, dest_dir: Path, filename: str | None = None) -> DownloadResult:
    """1件の添付資料をダウンロードする。失敗しても例外を投げず結果オブジェクトを返す。"""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        return DownloadResult(url=url, success=False, error=f"不正なURLスキームです: {url}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            resp.raise_for_status()
            # 拡張子はURLまたはContent-Typeから決める(リンク文字列には拡張子が無いため)
            safe_name = resolve_filename(url, filename, resp.headers.get("Content-Type"))
            dest_path = dest_dir / safe_name
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_FILE_SIZE_BYTES:
                return DownloadResult(url=url, success=False, error="ファイルサイズが上限を超えています")

            written = 0
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    written += len(chunk)
                    if written > MAX_FILE_SIZE_BYTES:
                        f.close()
                        dest_path.unlink(missing_ok=True)
                        return DownloadResult(url=url, success=False, error="ファイルサイズが上限を超えています")
                    f.write(chunk)

        return DownloadResult(url=url, success=True, local_path=str(dest_path))
    except requests.exceptions.Timeout:
        return DownloadResult(url=url, success=False, error="タイムアウトしました")
    except requests.exceptions.HTTPError as exc:
        return DownloadResult(url=url, success=False, error=f"HTTPエラー: {exc}")
    except requests.exceptions.RequestException as exc:
        return DownloadResult(url=url, success=False, error=f"接続エラー: {exc}")
    except OSError as exc:
        return DownloadResult(url=url, success=False, error=f"ファイル書き込みエラー: {exc}")


def download_specification(
    opportunity_id: int,
    attachment_urls: list[str],
    attachment_names: list[str] | None = None,
    base_dir: Path = ATTACHMENTS_DIR,
) -> list[DownloadResult]:
    """指定案件の添付資料をすべてダウンロードする(要件13)。"""
    dest_dir = base_dir / f"opportunity_{opportunity_id}"
    names = attachment_names or []
    results = []
    for i, url in enumerate(attachment_urls):
        name = names[i] if i < len(names) else None
        results.append(download_attachment(url, dest_dir, filename=name))
    return results
