"""青空文庫テキスト形式をXHTMLに変換するパーサー。"""

import re
from dataclasses import dataclass, field
from html import escape


@dataclass
class ImageRef:
    filename: str       # 元のファイル名 (例: fig54333_01.png)
    alt: str            # 説明文 / alt テキスト
    width: int = 0
    height: int = 0


@dataclass
class ParsedBook:
    title: str = ""
    author: str = ""
    body_xhtml: str = ""
    headings: list[tuple[int, str, str]] = field(default_factory=list)  # (level, id, text)
    images: list[ImageRef] = field(default_factory=list)  # 挿絵参照リスト


# 漢字判定用パターン（仝々〆〇ヶ含む）
_KANJI_CHARS = r"\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\u4EDD\u3005\u3006\u3007\u30F6"
_KANJI_RE = re.compile(f"[{_KANJI_CHARS}]")


def parse_aozora_text(text: str) -> ParsedBook:
    """青空文庫テキストを解析してParsedBookを返す。"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    header_lines, body_lines, _footer_lines = _split_sections(lines)

    book = ParsedBook()
    if header_lines:
        book.title = header_lines[0].strip()
        if len(header_lines) > 1:
            book.author = header_lines[1].strip()

    xhtml_lines = []
    heading_counter = 0
    in_block: dict[str, bool] = {}
    indent_stack: list[str] = []  # ネストされた字下げ用スタック

    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        i += 1

        if not line.strip():
            xhtml_lines.append("<p><br/></p>")
            continue

        # 挿絵注記: ［＃説明文（ファイル名、横XXX×縦YYY）入る］
        # ファイル名は英数字._-のみなので、説明文中の（）と区別可能
        m_img = re.match(
            r"[\s　]*［＃(.+)（([A-Za-z0-9_./-]+)、横(\d+)×縦(\d+)）入る］\s*$", line
        )
        if m_img:
            alt_text = m_img.group(1)
            filename = m_img.group(2)
            width = int(m_img.group(3))
            height = int(m_img.group(4))
            img_ref = ImageRef(filename=filename, alt=alt_text, width=width, height=height)
            book.images.append(img_ref)
            xhtml_lines.append(
                f'<div class="illustration">'
                f'<img src="../Images/{escape(filename)}" alt="{escape(alt_text)}"'
                f' width="{width}" height="{height}"/>'
                f'</div>'
            )
            continue

        # 改ページ
        if "［＃改ページ］" in line:
            line = line.replace("［＃改ページ］", "")
            if line.strip():
                xhtml_lines.append(f"<p>{_convert_inline(line)}</p>")
            xhtml_lines.append('<hr class="pagebreak"/>')
            continue

        # ブロック開始: ［＃ここからN字下げ］
        m = re.match(r"［＃ここから(\d+)字下げ(.*)］", line)
        if m:
            indent = m.group(1)
            xhtml_lines.append(f'<div style="margin-left: {indent}em;">')
            indent_stack.append(indent)
            continue

        # ブロック終了: ［＃ここで字下げ終わり］
        if re.match(r"［＃ここで字下げ終わり］", line):
            if indent_stack:
                xhtml_lines.append("</div>")
                indent_stack.pop()
            continue

        # ブロック開始: 傍点
        if line.strip() == "［＃傍点］":
            in_block["sesame"] = True
            xhtml_lines.append('<div class="sesame">')
            continue
        if line.strip() == "［＃傍点終わり］":
            if in_block.get("sesame"):
                xhtml_lines.append("</div>")
                in_block["sesame"] = False
            continue

        # ブロック見出し: ［＃ここから大見出し］
        m_heading_start = re.match(r"［＃ここから(大|中|小)見出し］", line)
        if m_heading_start:
            level = {"大": 1, "中": 2, "小": 3}[m_heading_start.group(1)]
            heading_lines_buf = []
            while i < len(body_lines):
                bline = body_lines[i]
                i += 1
                if re.match(r"［＃ここで(大|中|小)見出し終わり］", bline):
                    break
                heading_lines_buf.append(bline)
            heading_text = "".join(heading_lines_buf)
            heading_counter += 1
            hid = f"h{heading_counter}"
            book.headings.append((level, hid, heading_text))
            xhtml_lines.append(f'<h{level} id="{hid}">{_convert_inline(heading_text)}</h{level}>')
            continue

        # 行頭字下げ: ［＃N字下げ］
        m = re.match(r"［＃(\d+)字下げ］(.+)", line)
        if m:
            indent = m.group(1)
            content = m.group(2)
            xhtml_lines.append(f'<p style="margin-left: {indent}em;">{_convert_inline(content)}</p>')
            continue

        # 地付き
        m = re.match(r"［＃地付き］(.+)", line)
        if m:
            content = m.group(1)
            xhtml_lines.append(f'<p style="text-align: right;">{_convert_inline(content)}</p>')
            continue

        # 地寄せ（右寄せ）
        m = re.match(r"［＃地から(\d+)字上げ］(.+)", line)
        if m:
            content = m.group(2)
            xhtml_lines.append(f'<p style="text-align: right;">{_convert_inline(content)}</p>')
            continue

        # 通常行 — インライン注記処理後に見出し注記をチェック
        converted = _convert_line_with_heading(line, book, heading_counter)
        if converted[1] != heading_counter:
            heading_counter = converted[1]
        xhtml_lines.append(converted[0])

    book.body_xhtml = "\n".join(xhtml_lines)
    return book


def _split_sections(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    """ヘッダー、本文、フッターに分割する。"""
    header: list[str] = []
    body: list[str] = []
    footer: list[str] = []

    separator = "-------------------------------------------------------"
    sep_count = 0
    in_body = False
    body_started = False

    for line in lines:
        stripped = line.strip()

        if not in_body:
            if stripped.startswith(separator[:10]):
                sep_count += 1
                if sep_count == 2:
                    in_body = True
                continue
            if sep_count == 0:
                header.append(line)
        else:
            # フッター判定: 3行以上の空行連続後
            if not body_started:
                if stripped:
                    body_started = True
                    body.append(line)
                continue

            body.append(line)

    # ヘッダーセパレータが無い場合、最初の数行をヘッダーとして扱う
    if not in_body and not body:
        # セパレータなし: 最初の空行までがヘッダー、残りが本文
        header = []
        body = list(lines)
        for idx, ln in enumerate(lines):
            if not ln.strip():
                header = lines[:idx]
                body = lines[idx + 1:]
                break

    # フッター分離: 末尾に最も近い3行連続空行を探す
    if len(body) > 5:
        footer_start = len(body)
        consecutive_empty = 0
        last_block_end = -1  # 3連続空行ブロックの末尾位置（末尾側から最初に見つかったもの）
        for idx in range(len(body)):
            if not body[idx].strip():
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    last_block_end = idx
            else:
                consecutive_empty = 0
        if last_block_end >= 0:
            # 3連続空行ブロックの開始位置を求める
            footer_start = last_block_end
            while footer_start > 0 and not body[footer_start - 1].strip():
                footer_start -= 1
            footer = body[footer_start:]
            body = body[:footer_start]

    return header, body, footer


def _convert_line_with_heading(
    line: str, book: ParsedBook, counter: int
) -> tuple[str, int]:
    """行を変換し、見出し注記があればh要素にする。"""
    # インライン見出し: ○○［＃「○○」は大見出し］
    for size, level in [("大", 1), ("中", 2), ("小", 3)]:
        pattern = f"［＃「(.+?)」は{size}見出し］"
        m = re.search(pattern, line)
        if m:
            heading_text = m.group(1)
            counter += 1
            hid = f"h{counter}"
            book.headings.append((level, hid, heading_text))
            line = re.sub(pattern, "", line)
            converted = _convert_inline(line)
            return f'<h{level} id="{hid}">{converted}</h{level}>', counter

    # 通常段落
    return f"<p>{_convert_inline(line)}</p>", counter


def _convert_inline(text: str) -> str:
    """インライン注記をXHTMLに変換する。

    注記内の「対象テキスト」と本文側を正しく照合するため、
    「対象テキスト」を参照する注記はHTMLエスケープ前に処理する。
    """
    # --- エスケープ前に処理: 対象テキストの後方参照を使う注記 ---

    # 傍点（インライン）: ○○［＃「○○」に傍点］
    text = re.sub(
        r"(.+?)［＃「\1」に傍点］",
        lambda m: f'\x00SESAME_START\x00{m.group(1)}\x00SESAME_END\x00',
        text,
    )
    # 後方参照が効かない場合のフォールバック
    text = re.sub(
        r"［＃「(.+?)」に傍点］",
        lambda m: f'\x00SESAME_START\x00{m.group(1)}\x00SESAME_END\x00',
        text,
    )

    # 太字（インライン）
    text = re.sub(
        r"［＃「(.+?)」は太字］",
        lambda m: f'\x00B_START\x00{m.group(1)}\x00B_END\x00',
        text,
    )

    # 斜体（インライン）
    text = re.sub(
        r"［＃「(.+?)」は斜体］",
        lambda m: f'\x00I_START\x00{m.group(1)}\x00I_END\x00',
        text,
    )

    # 縦中横
    text = re.sub(
        r"［＃「(.+?)」は縦中横］",
        lambda m: f'\x00TCY_START\x00{m.group(1)}\x00TCY_END\x00',
        text,
    )

    # 傍線
    text = re.sub(
        r"［＃「(.+?)」に傍線］",
        lambda m: f'\x00UL_START\x00{m.group(1)}\x00UL_END\x00',
        text,
    )

    # --- HTMLエスケープ ---
    text = escape(text)

    # --- プレースホルダをHTMLタグに復元 ---
    text = text.replace("\x00SESAME_START\x00", '<em class="sesame">')
    text = text.replace("\x00SESAME_END\x00", "</em>")
    text = text.replace("\x00B_START\x00", "<b>")
    text = text.replace("\x00B_END\x00", "</b>")
    text = text.replace("\x00I_START\x00", "<i>")
    text = text.replace("\x00I_END\x00", "</i>")
    text = text.replace("\x00TCY_START\x00", '<span class="tcy">')
    text = text.replace("\x00TCY_END\x00", "</span>")
    text = text.replace("\x00UL_START\x00", '<span style="text-decoration: underline;">')
    text = text.replace("\x00UL_END\x00", "</span>")

    # くの字点
    text = text.replace("／＼", "〳〵")
    text = text.replace("／″＼", "〴〵")

    # ルビ: ｜base《ruby》
    text = re.sub(
        r"｜(.+?)《(.+?)》",
        r"<ruby>\1<rt>\2</rt></ruby>",
        text,
    )

    # ルビ: 漢字連続《ruby》（｜なし）
    text = re.sub(
        f"([{_KANJI_CHARS}]+)《(.+?)》",
        r"<ruby>\1<rt>\2</rt></ruby>",
        text,
    )

    # 残りのルビ（カタカナ等）
    text = re.sub(
        r"(\w+)《(.+?)》",
        r"<ruby>\1<rt>\2</rt></ruby>",
        text,
    )

    # 外字注記: ※［＃...］ → そのまま表示（完全変換は複雑なため説明を残す）
    text = re.sub(
        r"※［＃(.+?)］",
        lambda m: f'<span class="gaiji">[{m.group(1)}]</span>',
        text,
    )

    # その他の注記で未処理のもの: ［＃...］ → 非表示span
    text = re.sub(
        r"［＃(.+?)］",
        lambda m: f'<span class="note" hidden="">[{m.group(1)}]</span>',
        text,
    )

    return text
