"""Generic RSS/Atom collector — covers company blogs, news sites, HN feeds."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import feedparser
from dateutil import parser as dateparser

log = logging.getLogger(__name__)


def _parse_date(entry) -> str:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                continue
    return datetime.now(timezone.utc).isoformat()


def _clean_summary(text: str, limit: int = 600) -> str:
    if not text:
        return ""
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    except Exception:
        pass
    return text[:limit]


def collect(feeds: Iterable[dict], max_per_feed: int = 30) -> list[dict]:
    items: list[dict] = []
    for feed in feeds:
        name = feed["name"]
        url = feed["url"]
        topic_hint = feed.get("topic", "")
        try:
            parsed = feedparser.parse(url, request_headers={
                "User-Agent": "ai-news-tracker/1.0 (+local)"
            })
            if parsed.bozo and not parsed.entries:
                log.warning("Feed error %s: %s", name, parsed.bozo_exception)
                continue
            for entry in parsed.entries[:max_per_feed]:
                link = entry.get("link") or entry.get("id")
                if not link:
                    continue
                items.append({
                    "source": name,
                    "source_type": "rss",
                    "url": link,
                    "title": entry.get("title", "").strip(),
                    "summary": _clean_summary(entry.get("summary", "")),
                    "author": entry.get("author", ""),
                    "published_at": _parse_date(entry),
                    "topic": topic_hint,
                })
        except Exception as e:
            log.exception("RSS collect failed for %s: %s", name, e)
    return items
