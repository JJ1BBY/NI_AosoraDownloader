import io
import zipfile
from dataclasses import dataclass, field
from urllib.parse import urljoin
from urllib.request import urlopen, Request


USER_AGENT = "AosoraDownloader/1.0"

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg")


@dataclass
class DownloadResult:
    text: str
    images: dict[str, bytes] = field(default_factory=dict)  # {filename: data}


_ENCODING_MAP: dict[str, str] = {
    "ShiftJIS": "shift_jis",
    "UTF-8": "utf-8",
    "": "shift_jis",  # 空文字列の場合はShiftJISをデフォルトとする
}


def download_text(url: str, encoding: str = "ShiftJIS") -> DownloadResult:
    """テキストファイルURLからダウンロードし、テキストとzip同梱画像を返す。

    URLが.zipの場合はzip内の.txtファイルを展開し、
    同梱されている画像ファイルも一緒に取得する。
    """
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        data = resp.read()

    if url.endswith(".zip"):
        return _extract_from_zip(data, encoding)
    else:
        codec = _ENCODING_MAP.get(encoding, "shift_jis")
        return DownloadResult(text=data.decode(codec))


def download_image(image_filename: str, html_url: str) -> bytes:
    """HTMLファイルURLを基準に、挿絵の画像データをダウンロードする。

    画像はHTMLファイルと同じディレクトリに配置されている。
    zip内に同梱されていなかった場合のフォールバック用。
    """
    base_url = html_url.rsplit("/", 1)[0] + "/"
    image_url = urljoin(base_url, image_filename)
    req = Request(image_url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def _extract_from_zip(data: bytes, encoding: str) -> DownloadResult:
    """zipバイトデータからテキストと画像を抽出する。"""
    codec = _ENCODING_MAP.get(encoding, "shift_jis")
    text = ""
    images: dict[str, bytes] = {}

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith(".txt"):
                if not text:
                    with zf.open(name) as f:
                        text = f.read().decode(codec)
            elif any(lower.endswith(ext) for ext in _IMAGE_EXTENSIONS):
                with zf.open(name) as f:
                    # パスからファイル名部分だけ取得
                    basename = name.rsplit("/", 1)[-1]
                    images[basename] = f.read()

    if not text:
        raise ValueError("zip内に.txtファイルが見つかりません")

    return DownloadResult(text=text, images=images)
