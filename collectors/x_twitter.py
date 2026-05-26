"""X/Twitter collector via self-hosted RSSHub.

X's free API is not usable for monitoring. The only reliable free path is a
self-hosted RSSHub instance with an authenticated cookie. See
`scripts/setup_rsshub.md` for setup.

If `rsshub_url` is empty in config, this collector is a no-op.
"""
from __future__ import annotations

import logging

from . import rss as rss_mod

log = logging.getLogger(__name__)


def collect(rsshub_url: str, handles: list[str],
            max_per_handle: int = 20) -> list[dict]:
    if not rsshub_url:
        log.info("X collector skipped — rsshub_url not configured")
        return []
    feeds = [
        {
            "name": f"X @{h}",
            "url": f"{rsshub_url.rstrip('/')}/twitter/user/{h}",
            "topic": "Social Buzz",
        }
        for h in handles
    ]
    items = rss_mod.collect(feeds, max_per_feed=max_per_handle)
    for it in items:
        it["source_type"] = "x"
    return items
