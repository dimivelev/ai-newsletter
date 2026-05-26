"""Bluesky collector — public firehose via AT Protocol, no auth required."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger(__name__)

API = "https://public.api.bsky.app/xrpc"


def _resolve_did(handle: str) -> str | None:
    try:
        r = httpx.get(
            f"{API}/com.atproto.identity.resolveHandle",
            params={"handle": handle}, timeout=15,
        )
        r.raise_for_status()
        return r.json().get("did")
    except Exception as e:
        log.warning("resolveHandle failed for %s: %s", handle, e)
        return None


def collect(handles: list[str], lookback_hours: int = 24,
            max_per_handle: int = 30) -> list[dict]:
    items: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    for handle in handles:
        did = _resolve_did(handle)
        if not did:
            continue
        try:
            r = httpx.get(
                f"{API}/app.bsky.feed.getAuthorFeed",
                params={"actor": did, "limit": max_per_handle, "filter": "posts_no_replies"},
                timeout=15,
            )
            r.raise_for_status()
            feed = r.json().get("feed", [])
        except Exception as e:
            log.warning("bsky feed fetch failed for %s: %s", handle, e)
            continue
        for entry in feed:
            post = entry.get("post", {})
            record = post.get("record", {})
            text = (record.get("text") or "").strip()
            if not text:
                continue
            created = record.get("createdAt")
            try:
                pub = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                continue
            if pub < cutoff:
                continue
            rkey = post.get("uri", "").split("/")[-1]
            url = f"https://bsky.app/profile/{handle}/post/{rkey}"
            title = text.split("\n", 1)[0][:180]
            items.append({
                "source": f"Bluesky @{handle}",
                "source_type": "bluesky",
                "url": url,
                "title": title,
                "summary": text[:600],
                "author": handle,
                "published_at": pub.astimezone(timezone.utc).isoformat(),
                "topic": "Social Buzz",
            })
    return items
