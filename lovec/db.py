"""База ловца — один файл data/lovec.db (sqlite). Время везде в UTC, формат 'YYYY-MM-DD HH:MM:SS'."""
import sqlite3
from datetime import datetime, timezone

from config import DATA, DB_FILE

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    url TEXT PRIMARY KEY,          -- ссылка на сообщение: ключ, повтор не задваивается
    chat TEXT, author_id INTEGER, author_username TEXT, author_name TEXT,
    text TEXT, posted_at TEXT, phrase TEXT, found_at TEXT,
    score INTEGER, band TEXT, risk TEXT, rationale TEXT, scenario TEXT,
    scored_at TEXT, prefiltered INTEGER DEFAULT 0, notified_at TEXT
);
CREATE INDEX IF NOT EXISTS leads_score ON leads(score);
CREATE INDEX IF NOT EXISTS leads_posted ON leads(posted_at);
CREATE TABLE IF NOT EXISTS phrase_state (phrase TEXT PRIMARY KEY, last_run TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_utc(value):
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def to_local(value, fmt="%d.%m %H:%M"):
    d = parse_utc(value)
    return d.astimezone().strftime(fmt) if d else "?"


def open_db():
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def meta_get(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def meta_set(conn, key, value):
    conn.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    conn.commit()
