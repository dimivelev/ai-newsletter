"""Reddit collector — uses the public JSON endpoint (no auth, requires UA)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

UA = "ai-news-tracker/1.0 by local-user"


def collect(subs: list[dict], max_per_sub: int = 30) -> list[dict]:
    items: list[dict] = []
    headers = {"User-Agent": UA, "Accept": "application/json"}
    for s in subs:
        url = f"https://www.reddit.com/r/{s['sub']}/new.json?limit={max_per_sub}"
        try:
            r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log.warning("Reddit fetch failed for r/%s: %s", s["sub"], e)
            continue
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            link = d.get("permalink")
            if not link:
                continue
            ts = d.get("created_utc")
            pub = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
            items.append({
                "source": s["name"],
                "source_type": "reddit",
                "url": f"https://www.reddit.com{link}",
                "title": d.get("title", "").strip(),
                "summary": (d.get("selftext") or "")[:600],
                "author": d.get("author", ""),
                "published_at": pub.isoformat(),
                "topic": s.get("topic", "Social Buzz"),
            })
    return items
