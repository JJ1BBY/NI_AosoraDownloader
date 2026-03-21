"""バックグラウンド処理用のQThreadワーカー。"""

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


def _safe_filename(name: str) -> str:
    """ファイル名に使えない文字を除去する。"""
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "")
    return name[:50]
