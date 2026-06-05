import csv
from pathlib import Path

from .models import Work
from .ndc import parse_ndc_codes

ROLE_AUTHOR = "著者"
ROLE_TRANSLATOR = "翻訳者"


def load_catalog(csv_path: str | Path) -> list[Work]:
    """CSVファイルを読み込み、作品ID単位で集約したWorkリストを返す。"""
    csv_path = Path(csv_path)
    works_dict: dict[str, Work] = {}

    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            work_id = row["作品ID"]
            person_name = row["姓"] + row["名"]
            role = row["役割フラグ"]

            if work_id in works_dict:
                work = works_dict[work_id]
            else:
                work = Work(
                    work_id=work_id,
                    title=row["作品名"],
                    title_reading=row["作品名読み"],
                    subtitle=row["副題"],
                    classification=row["分類番号"],
                    charset_type=row["文字遣い種別"],
                    text_url=row["テキストファイルURL"],
                    text_encoding=row["テキストファイル符号化方式"],
                    html_url=row["XHTML/HTMLファイルURL"],
                    card_url=row["図書カードURL"],
                    release_date=row["公開日"],
                    last_updated=row["最終更新日"],
                    copyright=row["作品著作権フラグ"],
                )
                works_dict[work_id] = work

            if role == ROLE_AUTHOR and person_name not in work.authors:
                work.authors.append(person_name)
            elif role == ROLE_TRANSLATOR and person_name not in work.translators:
                work.translators.append(person_name)

    return list(works_dict.values())


def filter_by_ndc(works: list[Work], prefixes: set[str]) -> list[Work]:
    """NDCプレフィックスセットで作品を絞り込む。prefixesが空なら全件返す。"""
    if not prefixes:
        return works
    result = []
    for w in works:
        codes = parse_ndc_codes(w.classification)
        if any(c.startswith(p) for c in codes for p in prefixes):
            result.append(w)
    return result


def search_works(
    works: list[Work],
    author: str = "",
    title: str = "",
) -> list[Work]:
    """著者名とタイトルで作品を絞り込む（AND条件、部分一致）。"""
    results = works
    if author:
        author_lower = author.lower()
        results = [
            w for w in results
            if any(author_lower in a.lower() for a in w.authors)
            or any(author_lower in t.lower() for t in w.translators)
        ]
    if title:
        title_lower = title.lower()
        results = [
            w for w in results
            if title_lower in w.title.lower()
            or title_lower in w.title_reading.lower()
        ]
    return results
