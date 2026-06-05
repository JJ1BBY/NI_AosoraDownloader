"""バックグラウンド処理用のQThreadワーカー。"""

import io
import urllib.request
import zipfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from aozora.downloader import download_image, download_text
from aozora.epub_writer import write_epub
from aozora.models import Work
from aozora.parser import parse_aozora_text


class DownloadConvertWorker(QThread):
    """作品のダウンロード→テキスト解析→EPUB変換を実行するワーカー。"""

    progress = Signal(int, str)  # (percent, message)
    finished_all = Signal(int, int)  # (success_count, error_count)
    error_occurred = Signal(str, str)  # (work_id, error_message)

    def __init__(
        self,
        works: list[Work],
        output_dir: str,
        include_images: bool = True,
        author_in_filename: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.works = works
        self.output_dir = output_dir
        self.include_images = include_images
        self.author_in_filename = author_in_filename
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.works)
        success = 0
        errors = 0

        for i, work in enumerate(self.works):
            if self._cancelled:
                break

            pct = int((i / total) * 100)
            self.progress.emit(pct, f"ダウンロード中: {work.title}")

            try:
                # テキスト＆zip同梱画像をダウンロード
                result = download_text(work.text_url, work.text_encoding)

                # テキスト解析
                self.progress.emit(pct, f"変換中: {work.title}")
                parsed = parse_aozora_text(result.text)
                if not parsed.title:
                    parsed.title = work.title
                if not parsed.author:
                    parsed.author = work.authors_display

                # 画像収集: zip同梱分を優先、不足分はHTTPで取得
                image_data: dict[str, bytes] = {}
                if self.include_images and parsed.images:
                    for img_ref in parsed.images:
                        if self._cancelled:
                            break
                        if img_ref.filename in result.images:
                            # zip同梱画像を使用
                            image_data[img_ref.filename] = result.images[img_ref.filename]
                        elif work.html_url:
                            # フォールバック: HTTPダウンロード
                            self.progress.emit(pct, f"画像取得中: {img_ref.filename}")
                            try:
                                data = download_image(img_ref.filename, work.html_url)
                                image_data[img_ref.filename] = data
                            except Exception:
                                pass  # 画像取得失敗はスキップ

                # EPUB生成
                safe_title = _safe_filename(work.title)
                if self.author_in_filename and work.authors:
                    safe_author = _safe_filename(work.authors_display)
                    filename = f"[{safe_author}] {safe_title}.epub"
                else:
                    filename = f"{safe_title}.epub"
                output_path = f"{self.output_dir}/{filename}"
                write_epub(
                    parsed,
                    output_path,
                    work_id=work.work_id,
                    authors=work.authors,
                    translators=work.translators,
                    include_images=self.include_images,
                    image_data=image_data,
                )
                success += 1

            except Exception as e:
                errors += 1
                self.error_occurred.emit(work.work_id, str(e))

        self.progress.emit(100, "完了")
        self.finished_all.emit(success, errors)


CATALOG_ZIP_URL = "https://www.aozora.gr.jp/index_pages/list_person_all_extended_utf8.zip"
_CHUNK = 65536  # 64 KB


class CatalogUpdateWorker(QThread):
    """青空文庫カタログCSVをダウンロード・展開して上書き保存するワーカー。"""

    progress = Signal(int, str)   # (percent, message)
    completed = Signal()          # QThread.finished を上書きしないよう別名
    update_error = Signal(str)

    def __init__(self, dest_csv: Path, parent=None):
        super().__init__(parent)
        self._dest = dest_csv

    def run(self):
        try:
            self.progress.emit(0, "カタログをダウンロード中...")
            req = urllib.request.Request(
                CATALOG_ZIP_URL,
                headers={"User-Agent": "AosoraDownloader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                buf = io.BytesIO()
                downloaded = 0
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    buf.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = min(int(downloaded / total * 80), 80)
                        self.progress.emit(pct, f"ダウンロード中... {downloaded // 1024} KB")

            self.progress.emit(85, "ZIPを展開中...")
            buf.seek(0)
            with zipfile.ZipFile(buf) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    raise RuntimeError("ZIP内にCSVファイルが見つかりません")
                csv_data = zf.read(csv_names[0])

            self.progress.emit(95, "CSVファイルを保存中...")
            # 書き込み中クラッシュで元ファイルが破損しないよう一時ファイル経由で置換
            tmp = self._dest.with_suffix(".tmp")
            tmp.write_bytes(csv_data)
            tmp.replace(self._dest)

            self.progress.emit(100, "カタログ更新完了")
            self.completed.emit()
        except Exception as e:
            self.update_error.emit(str(e))


def _safe_filename(name: str) -> str:
    """ファイル名に使えない文字を除去する。"""
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "")
    return name[:50]
