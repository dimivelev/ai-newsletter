"""Orchestrator: collect → dedupe → classify → store.

Run manually:
    python scheduler.py

Scheduled via launchd (see scripts/com.ainews.tracker.plist).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))

from collectors import arxiv_c, bluesky, hn, reddit_c, rss, x_twitter
from storage import db
import classifier

LOG_FILE = ROOT / "logs" / "scheduler.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("scheduler")


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def collect_all(cfg: dict) -> list[dict]:
    all_items: list[dict] = []

    log.info("Collecting RSS feeds (%d)...", len(cfg["rss_feeds"]))
    all_items.extend(rss.collect(cfg["rss_feeds"], cfg["max_items_per_source"]))

    log.info("Collecting arXiv (%d cats)...", len(cfg["arxiv_categories"]))
    all_items.extend(arxiv_c.collect(
        cfg["arxiv_categories"], cfg["lookback_hours"],
        cfg["max_items_per_source"],
    ))

    log.info("Collecting Reddit (%d subs)...", len(cfg["reddit_subs"]))
    all_items.extend(reddit_c.collect(cfg["reddit_subs"], cfg["max_items_per_source"]))

    log.info("Collecting Hacker News...")
    all_items.extend(hn.collect(cfg["lookback_hours"]))

    log.info("Collecting Bluesky (%d handles)...", len(cfg["bluesky_handles"]))
    all_items.extend(bluesky.collect(
        cfg["bluesky_handles"], cfg["lookback_hours"],
        cfg["max_items_per_source"],
    ))

    if cfg.get("rsshub_url"):
        log.info("Collecting X via RSSHub (%d handles)...", len(cfg["x_handles"]))
        all_items.extend(x_twitter.collect(
            cfg["rsshub_url"], cfg["x_handles"], cfg["max_items_per_source"],
        ))
    else:
        log.info("X/RSSHub not configured — skipping.")

    log.info("Collected %d raw items.", len(all_items))
    return all_items


def run() -> None:
    db.init_db()
    cfg = load_config()
    run_id = db.start_run()
    errors: list[str] = []
    items_new = 0

    try:
        raw = collect_all(cfg)

        # dedupe by URL in-memory before DB insert
        seen: set[str] = set()
        unique: list[dict] = []
        for it in raw:
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            unique.append(it)

        # insert new items (classification deferred)
        new_items: list[dict] = []
        for it in unique:
            if db.insert_item(it):
                items_new += 1
                new_items.append(it)

        log.info("Inserted %d new items.", items_new)

        # classify unclassified items (new + any leftovers from prior failed runs)
        unclassified = db.fetch_unclassified(limit=500)
        if unclassified:
            clf = classifier.get_classifier(cfg)
            log.info("Classifying %d items via %s (%s)...",
                     len(unclassified), cfg.get("provider", "anthropic"),
                     clf.model)
            item_dicts = [dict(r) for r in unclassified]
            labels = clf.classify_batch(item_dicts, cfg["topics"])
            for row, lbl in zip(unclassified, labels):
                db.update_classification(
                    url=row["url"],
                    topic=lbl.get("topic", "Applications"),
                    importance=int(lbl.get("importance", 1)),
                    why=lbl.get("why", "")[:300],
                    tldr=lbl.get("tldr", "")[:500],
                )
            log.info("Classification complete.")
    except Exception as e:
        log.exception("Run failed: %s", e)
        errors.append(str(e))
    finally:
        db.finish_run(run_id, found=len(raw) if 'raw' in locals() else 0,
                      new=items_new, errors="; ".join(errors))


if __name__ == "__main__":
    run()
