"""SQLiteによるカタログキャッシュ。CSVのmtimeが同じなら高速に返す。"""
import json
import sqlite3
from pathlib import Path

from .models import Work

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS works (
    work_id TEXT PRIMARY KEY,
    title TEXT, title_reading TEXT, subtitle TEXT,
    authors TEXT, translators TEXT,
    classification TEXT, charset_type TEXT,
    text_url TEXT, text_encoding TEXT,
    html_url TEXT, card_url TEXT,
    release_date TEXT, last_updated TEXT, copyright TEXT
);
"""

_INSERT = (
    "INSERT OR REPLACE INTO works VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)


def load(db_path: Path, csv_mtime: str) -> list[Work] | None:
    """キャッシュが有効なら Works を返す。無効・破損時は None。"""
    if not db_path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        row = con.execute(
            "SELECT value FROM meta WHERE key='csv_mtime'"
        ).fetchone()
        if not row or row[0] != csv_mtime:
            con.close()
            return None
        rows = con.execute("SELECT * FROM works").fetchall()
        con.close()
    except Exception:
        return None

    return [
        Work(
            work_id=r[0], title=r[1], title_reading=r[2], subtitle=r[3],
            authors=json.loads(r[4]), translators=json.loads(r[5]),
            classification=r[6], charset_type=r[7],
            text_url=r[8], text_encoding=r[9],
            html_url=r[10], card_url=r[11],
            release_date=r[12], last_updated=r[13], copyright=r[14],
        )
        for r in rows
    ]


def save(works: list[Work], db_path: Path, csv_mtime: str) -> None:
    """Works を SQLite に保存する。失敗しても例外を伝播しない。"""
    try:
        con = sqlite3.connect(db_path)
        con.executescript(_SCHEMA)
        con.execute("DELETE FROM meta")
        con.execute("INSERT INTO meta VALUES ('csv_mtime', ?)", (csv_mtime,))
        con.execute("DELETE FROM works")
        con.executemany(
            _INSERT,
            [
                (
                    w.work_id, w.title, w.title_reading, w.subtitle,
                    json.dumps(w.authors, ensure_ascii=False),
                    json.dumps(w.translators, ensure_ascii=False),
                    w.classification, w.charset_type,
                    w.text_url, w.text_encoding,
                    w.html_url, w.card_url,
                    w.release_date, w.last_updated, w.copyright,
                )
                for w in works
            ],
        )
        con.commit()
        con.close()
    except Exception:
        pass
