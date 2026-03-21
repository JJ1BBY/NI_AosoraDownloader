"""EPUB 3.0ファイルを生成するモジュール。"""

import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .parser import ImageRef, ParsedBook

MIMETYPE = "application/epub+zip"

CONTAINER_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

STYLE_CSS = """\
@charset "UTF-8";
html {
  writing-mode: vertical-rl;
  -webkit-writing-mode: vertical-rl;
  -epub-writing-mode: vertical-rl;
}
body {
  font-family: serif;
  line-height: 1.8;
  margin: 1em;
}
h1 { font-size: 1.5em; margin: 2em 0.5em; }
h2 { font-size: 1.3em; margin: 1.5em 0.5em; }
h3 { font-size: 1.1em; margin: 1em 0.5em; }
p { text-indent: 1em; margin: 0; }
ruby rt { font-size: 0.5em; }
em.sesame {
  text-emphasis-style: sesame;
  -webkit-text-emphasis-style: sesame;
  font-style: normal;
}
span.tcy {
  text-combine-upright: all;
  -webkit-text-combine: horizontal;
  -epub-text-combine: horizontal;
}
span.gaiji {
  font-size: 0.8em;
  color: #666;
}
hr.pagebreak {
  page-break-after: always;
  border: none;
  margin: 0;
}
div.illustration {
  text-align: center;
  margin: 1em 0;
}
div.illustration img {
  max-width: 100%;
  max-height: 100%;
}
/* タイトルページ */
body.titlepage {
  writing-mode: vertical-rl;
  -webkit-writing-mode: vertical-rl;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100%;
  text-align: center;
}
body.titlepage h1 {
  font-size: 2em;
  margin: 1em 0.5em;
  border-right: 3px solid #333;
  padding-right: 0.5em;
}
body.titlepage .author {
  font-size: 1.2em;
  margin: 0.5em;
}
body.titlepage .translator {
  font-size: 1em;
  color: #555;
  margin: 0.3em;
}
body.titlepage .source {
  font-size: 0.8em;
  color: #888;
  margin-top: 2em;
}
/* カバーページ */
body.coverpage {
  writing-mode: horizontal-tb;
  margin: 0;
  padding: 0;
  text-align: center;
}
body.coverpage svg {
  width: 100%;
  height: 100%;
}
"""


def write_epub(
    book: ParsedBook,
    output_path: str | Path,
    work_id: str = "",
    authors: list[str] | None = None,
    translators: list[str] | None = None,
    include_images: bool = True,
    image_data: dict[str, bytes] | None = None,
) -> Path:
    """ParsedBookからEPUBファイルを生成する。

    Args:
        book: 解析済み書籍データ
        output_path: 出力ファイルパス
        work_id: 作品ID
        authors: 著者名リスト
        translators: 翻訳者名リスト
        include_images: 画像を含めるか
        image_data: {ファイル名: バイトデータ} の辞書
    """
    output_path = Path(output_path)
    book_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"aozora:{work_id}")) if work_id else str(uuid.uuid4())
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    author_str = "、".join(authors) if authors else book.author
    translator_str = "、".join(translators) if translators else ""
    title = book.title or "無題"

    # 画像を含めない場合、本文から画像タグを除去
    body_xhtml = book.body_xhtml
    images_to_include: list[ImageRef] = []
    actual_image_data: dict[str, bytes] = {}

    if include_images and image_data:
        images_to_include = [
            img for img in book.images if img.filename in image_data
        ]
        actual_image_data = {
            img.filename: image_data[img.filename]
            for img in images_to_include
        }
    elif not include_images:
        # 画像タグを除去
        import re
        body_xhtml = re.sub(r'<div class="illustration">.*?</div>', "", body_xhtml, flags=re.DOTALL)

    has_cover = include_images  # カバー画像（SVG生成）は常に含める
    content_opf = _build_content_opf(
        book_id, title, author_str, modified,
        has_cover=has_cover,
        images=images_to_include,
    )
    toc_xhtml = _build_toc_xhtml(title, book.headings)
    toc_ncx = _build_toc_ncx(book_id, title, book.headings)
    titlepage_xhtml = _build_titlepage_xhtml(title, author_str, translator_str)
    main_xhtml = _build_main_xhtml(title, body_xhtml)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetypeは無圧縮で最初に格納
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.xhtml", toc_xhtml)
        zf.writestr("OEBPS/toc.ncx", toc_ncx)
        zf.writestr("OEBPS/Styles/style.css", STYLE_CSS)
        if has_cover:
            cover_xhtml = _build_cover_xhtml(title, author_str)
            zf.writestr("OEBPS/Text/cover.xhtml", cover_xhtml)
        zf.writestr("OEBPS/Text/titlepage.xhtml", titlepage_xhtml)
        zf.writestr("OEBPS/Text/main.xhtml", main_xhtml)

        # 画像ファイルを格納
        for filename, data in actual_image_data.items():
            zf.writestr(f"OEBPS/Images/{filename}", data)

    return output_path


def _build_content_opf(
    book_id: str,
    title: str,
    author: str,
    modified: str,
    has_cover: bool = False,
    images: list[ImageRef] | None = None,
) -> str:
    images = images or []

    # manifest items
    manifest_items = [
        '    <item id="nav" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '    <item id="css" href="Styles/style.css" media-type="text/css"/>',
    ]
    if has_cover:
        manifest_items.append(
            '    <item id="cover" href="Text/cover.xhtml" media-type="application/xhtml+xml" properties="svg"/>'
        )
    manifest_items.append(
        '    <item id="titlepage" href="Text/titlepage.xhtml" media-type="application/xhtml+xml"/>'
    )
    manifest_items.append(
        '    <item id="main" href="Text/main.xhtml" media-type="application/xhtml+xml"/>'
    )

    for i, img in enumerate(images):
        ext = img.filename.rsplit(".", 1)[-1].lower()
        media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(ext, "image/png")
        manifest_items.append(
            f'    <item id="img{i}" href="Images/{_xml_escape(img.filename)}" media-type="{media_type}"/>'
        )

    manifest_str = "\n".join(manifest_items)

    # spine items
    spine_items = []
    if has_cover:
        spine_items.append('    <itemref idref="cover"/>')
    spine_items.append('    <itemref idref="titlepage"/>')
    spine_items.append('    <itemref idref="main"/>')
    spine_str = "\n".join(spine_items)

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="BookId" xml:lang="ja">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:uuid:{book_id}</dc:identifier>
    <dc:title>{_xml_escape(title)}</dc:title>
    <dc:language>ja</dc:language>
    <dc:creator>{_xml_escape(author)}</dc:creator>
    <dc:source>https://www.aozora.gr.jp/</dc:source>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
{manifest_str}
  </manifest>
  <spine toc="ncx" page-progression-direction="rtl">
{spine_str}
  </spine>
</package>"""


def _build_cover_xhtml(title: str, author: str) -> str:
    """SVGベースのカバーページを生成する。"""
    esc_title = _xml_escape(title)
    esc_author = _xml_escape(author)

    # タイトルが長い場合は改行して複数tspanに分割
    title_lines = _wrap_text(title, 10)
    title_tspans = ""
    start_y = max(200, 400 - len(title_lines) * 50)
    for i, tl in enumerate(title_lines):
        title_tspans += f'      <tspan x="300" dy="{0 if i == 0 else 60}">{_xml_escape(tl)}</tspan>\n'

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja">
<head>
  <title>{esc_title}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body class="coverpage">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800" preserveAspectRatio="xMidYMid meet">
    <rect width="600" height="800" fill="#f5f0e8"/>
    <rect x="30" y="30" width="540" height="740" fill="none" stroke="#8b7355" stroke-width="2"/>
    <rect x="35" y="35" width="530" height="730" fill="none" stroke="#8b7355" stroke-width="0.5"/>
    <text text-anchor="middle" font-family="serif" font-size="42" fill="#333" y="{start_y}">
{title_tspans}    </text>
    <line x1="200" y1="550" x2="400" y2="550" stroke="#8b7355" stroke-width="1"/>
    <text text-anchor="middle" font-family="serif" font-size="24" fill="#555" x="300" y="600">
      {esc_author}
    </text>
    <text text-anchor="middle" font-family="serif" font-size="14" fill="#999" x="300" y="720">
      青空文庫
    </text>
  </svg>
</body>
</html>"""


def _build_titlepage_xhtml(title: str, author: str, translator: str) -> str:
    """タイトルページXHTMLを生成する。"""
    esc_title = _xml_escape(title)
    esc_author = _xml_escape(author)

    translator_html = ""
    if translator:
        translator_html = f'\n  <p class="translator">{_xml_escape(translator)} 訳</p>'

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja">
<head>
  <title>{esc_title}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body class="titlepage">
  <h1>{esc_title}</h1>
  <p class="author">{esc_author}</p>{translator_html}
  <p class="source">青空文庫</p>
</body>
</html>"""


def _build_toc_ncx(
    book_id: str,
    title: str,
    headings: list[tuple[int, str, str]],
) -> str:
    """EPUB2互換のNCX目次を生成する。"""
    nav_points = ""
    if headings:
        for i, (level, hid, text) in enumerate(headings, 1):
            nav_points += f"""\
    <navPoint id="navPoint-{i}" playOrder="{i}">
      <navLabel><text>{_xml_escape(text)}</text></navLabel>
      <content src="Text/main.xhtml#{hid}"/>
    </navPoint>
"""
    else:
        nav_points = f"""\
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>{_xml_escape(title)}</text></navLabel>
      <content src="Text/main.xhtml"/>
    </navPoint>
"""

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{_xml_escape(title)}</text></docTitle>
  <navMap>
{nav_points}  </navMap>
</ncx>"""


def _build_toc_xhtml(title: str, headings: list[tuple[int, str, str]]) -> str:
    toc_items = ""
    if headings:
        for level, hid, text in headings:
            indent = "      " + "  " * (level - 1)
            toc_items += f'{indent}<li><a href="Text/main.xhtml#{hid}">{_xml_escape(text)}</a></li>\n'
    else:
        toc_items = f'      <li><a href="Text/main.xhtml">{_xml_escape(title)}</a></li>\n'

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ja">
<head>
  <title>目次</title>
</head>
<body>
  <nav epub:type="toc">
    <h1>目次</h1>
    <ol>
{toc_items}    </ol>
  </nav>
</body>
</html>"""


def _build_main_xhtml(title: str, body_xhtml: str) -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ja">
<head>
  <title>{_xml_escape(title)}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body>
{body_xhtml}
</body>
</html>"""


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """テキストを指定文字数で折り返す。"""
    lines = []
    while text:
        lines.append(text[:max_chars])
        text = text[max_chars:]
    return lines
