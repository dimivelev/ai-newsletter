"""Hacker News collector using the Algolia search API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

API = "https://hn.algolia.com/api/v1/search_by_date"
QUERIES = [
    "AI OR LLM OR AGI",
    "OpenAI OR Anthropic OR DeepMind",
    "GPT OR Claude OR Gemini OR Llama",
    "NVIDIA OR TPU OR GPU AI",
]


def collect(lookback_hours: int = 24, min_points: int = 30,
            max_per_query: int = 40) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for q in QUERIES:
        try:
            r = httpx.get(API, params={
                "query": q,
                "tags": "story",
                "numericFilters": f"points>={min_points}",
                "hitsPerPage": max_per_query,
            }, timeout=15)
            r.raise_for_status()
            hits = r.json().get("hits", [])
        except Exception as e:
            log.warning("HN query failed (%s): %s", q, e)
            continue
        for h in hits:
            url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
            if url in seen:
                continue
            seen.add(url)
            ts = h.get("created_at_i")
            pub = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
            items.append({
                "source": "Hacker News",
                "source_type": "hn",
                "url": url,
                "title": h.get("title", "").strip(),
                "summary": f"HN points: {h.get('points', 0)}, comments: {h.get('num_comments', 0)}",
                "author": h.get("author", ""),
                "published_at": pub.isoformat(),
                "topic": "Social Buzz",
            })
    return items
