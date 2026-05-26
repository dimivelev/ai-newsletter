"""arXiv collector — uses the arxiv Python package."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import arxiv

log = logging.getLogger(__name__)


def collect(categories: list[str], lookback_hours: int = 24,
            max_per_cat: int = 30) -> list[dict]:
    items: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    client = arxiv.Client(page_size=max_per_cat, delay_seconds=10.0, num_retries=5)
    for cat in categories:
        try:
            search = arxiv.Search(
                query=f"cat:{cat}",
                max_results=max_per_cat,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            for r in client.results(search):
                pub = r.published
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                if pub < cutoff:
                    break
                items.append({
                    "source": f"arXiv {cat}",
                    "source_type": "arxiv",
                    "url": r.entry_id,
                    "title": r.title.strip().replace("\n", " "),
                    "summary": r.summary.strip().replace("\n", " ")[:800],
                    "author": ", ".join(a.name for a in r.authors[:5]),
                    "published_at": pub.astimezone(timezone.utc).isoformat(),
                    "topic": "Research Papers",
                })
        except Exception as e:
            log.exception("arXiv collect failed for %s: %s", cat, e)
    return items
