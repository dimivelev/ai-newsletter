"""FastAPI dashboard for AI News Tracker."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import db  # noqa: E402

app = FastAPI(title="AI News Tracker")
templates = Jinja2Templates(directory=str(ROOT / "web" / "templates"))
app.mount("/static", StaticFiles(directory=str(ROOT / "web" / "static")), name="static")


def load_topics() -> list[str]:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)["topics"]


def group_by_importance(rows) -> dict:
    buckets = {3: [], 2: [], 1: [], None: []}
    for r in rows:
        buckets.setdefault(r["importance"], []).append(r)
    return buckets


@app.get("/", response_class=HTMLResponse)
def index(request: Request, topic: str = "All", hours: int = 168):
    topics = load_topics()
    rows = db.fetch_items(topic=topic, since_hours=hours, limit=500)
    grouped = group_by_importance(rows)
    daily = db.daily_counts(days=14)
    # Tab counts reflect the selected window so users can see which tabs
    # have content without clicking through.
    topic_cnt = db.topic_counts(since_hours=hours)
    last = db.last_run()
    total_today = sum(n for d, n in daily if d == datetime.utcnow().strftime("%Y-%m-%d"))

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "topics": ["All"] + topics,
            "active_topic": topic,
            "hours": hours,
            "grouped": grouped,
            "daily": daily,
            "topic_cnt": topic_cnt,
            "last_run": last,
            "total_today": total_today,
        },
    )


@app.get("/health")
def health():
    return {"ok": True, "last_run": dict(db.last_run()) if db.last_run() else None}
