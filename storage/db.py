"""SQLite storage for AI news items."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "news.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    source_type     TEXT NOT NULL,       -- rss | arxiv | reddit | bluesky | x | hn
    url             TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    summary         TEXT,
    author          TEXT,
    published_at    TEXT NOT NULL,       -- ISO 8601 UTC
    collected_at    TEXT NOT NULL,
    topic           TEXT,                -- classified topic
    importance      INTEGER,             -- 1=routine, 2=notable, 3=major
    importance_why  TEXT,                -- short reason from classifier
    tldr            TEXT,                -- 1-sentence summary from classifier
    raw_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_topic     ON items(topic);
CREATE INDEX IF NOT EXISTS idx_items_importance ON items(importance DESC);
CREATE INDEX IF NOT EXISTS idx_items_collected ON items(collected_at DESC);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    items_found     INTEGER DEFAULT 0,
    items_new       INTEGER DEFAULT 0,
    errors          TEXT
);

CREATE TABLE IF NOT EXISTS bookmarks (
    item_id         INTEGER PRIMARY KEY,
    created_at      TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(SCHEMA)


@contextmanager
def conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def insert_item(item: dict) -> bool:
    """Insert item. Returns True if new, False if duplicate URL."""
    now = datetime.now(timezone.utc).isoformat()
    with conn() as con:
        try:
            con.execute(
                """INSERT INTO items
                   (source, source_type, url, title, summary, author,
                    published_at, collected_at, topic, importance,
                    importance_why, tldr, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["source"],
                    item["source_type"],
                    item["url"],
                    item["title"],
                    item.get("summary"),
                    item.get("author"),
                    item["published_at"],
                    now,
                    item.get("topic"),
                    item.get("importance"),
                    item.get("importance_why"),
                    item.get("tldr"),
                    item.get("raw_json"),
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def update_classification(url: str, topic: str, importance: int,
                          why: str, tldr: str) -> None:
    with conn() as con:
        con.execute(
            "UPDATE items SET topic=?, importance=?, importance_why=?, tldr=? WHERE url=?",
            (topic, importance, why, tldr, url),
        )


def fetch_unclassified(limit: int = 100) -> list[sqlite3.Row]:
    """Items with no importance yet — classifier hasn't seen them.
    We key on importance, not topic, because feeds supply a topic hint."""
    with conn() as con:
        return con.execute(
            "SELECT * FROM items WHERE importance IS NULL ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def fetch_items(topic: Optional[str] = None, since_hours: int = 168,
                limit: int = 200, q: Optional[str] = None,
                sources: Optional[list[str]] = None) -> list[sqlite3.Row]:
    sql = """SELECT items.*, (bookmarks.item_id IS NOT NULL) AS is_bookmarked
             FROM items
             LEFT JOIN bookmarks ON items.id = bookmarks.item_id
             WHERE datetime(items.published_at) >= datetime('now', ?)"""
    params: list = [f"-{since_hours} hours"]
    if topic and topic != "All":
        sql += " AND items.topic = ?"
        params.append(topic)
    if q:
        sql += " AND (items.title LIKE ? OR items.tldr LIKE ? OR items.summary LIKE ?)"
        q_wildcard = f"%{q}%"
        params.extend([q_wildcard, q_wildcard, q_wildcard])
    if sources:
        placeholders = ", ".join("?" for _ in sources)
        sql += f" AND items.source_type IN ({placeholders})"
        params.extend(sources)
    sql += " ORDER BY items.importance DESC NULLS LAST, items.published_at DESC LIMIT ?"
    params.append(limit)
    with conn() as con:
        return con.execute(sql, params).fetchall()


def daily_counts(days: int = 14) -> list[tuple[str, int]]:
    with conn() as con:
        rows = con.execute(
            """SELECT date(published_at) AS d, COUNT(*) AS n
               FROM items
               WHERE date(published_at) >= date('now', ?)
               GROUP BY d ORDER BY d DESC""",
            (f"-{days} days",),
        ).fetchall()
    return [(r["d"], r["n"]) for r in rows]


def topic_counts(since_hours: int = 24, q: Optional[str] = None,
                 sources: Optional[list[str]] = None) -> dict[str, int]:
    sql = """SELECT topic, COUNT(*) AS n FROM items
             WHERE datetime(published_at) >= datetime('now', ?)"""
    params: list = [f"-{since_hours} hours"]
    if q:
        sql += " AND (title LIKE ? OR tldr LIKE ? OR summary LIKE ?)"
        q_wildcard = f"%{q}%"
        params.extend([q_wildcard, q_wildcard, q_wildcard])
    if sources:
        placeholders = ", ".join("?" for _ in sources)
        sql += f" AND source_type IN ({placeholders})"
        params.extend(sources)
    sql += " GROUP BY topic"
    with conn() as con:
        rows = con.execute(sql, params).fetchall()
    return {r["topic"] or "Unclassified": r["n"] for r in rows}


def start_run() -> int:
    with conn() as con:
        cur = con.execute(
            "INSERT INTO runs (started_at) VALUES (?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        return cur.lastrowid


def finish_run(run_id: int, found: int, new: int, errors: str = "") -> None:
    with conn() as con:
        con.execute(
            """UPDATE runs SET finished_at=?, items_found=?, items_new=?, errors=?
               WHERE id=?""",
            (datetime.now(timezone.utc).isoformat(), found, new, errors, run_id),
        )


def last_run() -> Optional[sqlite3.Row]:
    with conn() as con:
        return con.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()


def add_bookmark(item_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO bookmarks (item_id, created_at) VALUES (?, ?)",
            (item_id, now),
        )


def remove_bookmark(item_id: int) -> None:
    with conn() as con:
        con.execute("DELETE FROM bookmarks WHERE item_id = ?", (item_id,))


def count_bookmarks(q: Optional[str] = None,
                    sources: Optional[list[str]] = None) -> int:
    sql = """SELECT COUNT(*) FROM bookmarks
             INNER JOIN items ON bookmarks.item_id = items.id
             WHERE 1=1"""
    params: list = []
    if q:
        sql += " AND (items.title LIKE ? OR items.tldr LIKE ? OR items.summary LIKE ?)"
        q_wildcard = f"%{q}%"
        params.extend([q_wildcard, q_wildcard, q_wildcard])
    if sources:
        placeholders = ", ".join("?" for _ in sources)
        sql += f" AND items.source_type IN ({placeholders})"
        params.extend(sources)
    with conn() as con:
        row = con.execute(sql, params).fetchone()
        return row[0] if row else 0


def fetch_bookmarked_items(q: Optional[str] = None,
                           sources: Optional[list[str]] = None) -> list[sqlite3.Row]:
    sql = """SELECT items.*, 1 AS is_bookmarked
             FROM items
             INNER JOIN bookmarks ON items.id = bookmarks.item_id
             WHERE 1=1"""
    params: list = []
    if q:
        sql += " AND (items.title LIKE ? OR items.tldr LIKE ? OR items.summary LIKE ?)"
        q_wildcard = f"%{q}%"
        params.extend([q_wildcard, q_wildcard, q_wildcard])
    if sources:
        placeholders = ", ".join("?" for _ in sources)
        sql += f" AND items.source_type IN ({placeholders})"
        params.extend(sources)
    sql += " ORDER BY bookmarks.created_at DESC"
    with conn() as con:
        return con.execute(sql, params).fetchall()
