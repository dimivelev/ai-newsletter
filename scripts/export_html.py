"""Export the dashboard to a single self-contained HTML file.

Reads the live SQLite, reads the live CSS file, renders the index template
with `mode='export'` and `inline_css=<full css>`, then writes it to
`export/dispatch.html`. The result has no external dependencies — open it
in any browser, attach to a LinkedIn post, host on Netlify, e-mail it. No
API keys are present anywhere in the file.

Usage:
    python scripts/export_html.py [hours] [topic]
    python scripts/export_html.py 168 All        # default
    python scripts/export_html.py 72             # last 72h, all topics
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import db  # noqa: E402

HOURS = int(sys.argv[1]) if len(sys.argv) > 1 else 168
TOPIC = sys.argv[2] if len(sys.argv) > 2 else "All"

OUT_DIR = ROOT / "export"
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / "dispatch.html"

CSS_FILE = ROOT / "web" / "static" / "style.css"
TEMPLATE_DIR = ROOT / "web" / "templates"


def group_by_importance(rows):
    buckets = {3: [], 2: [], 1: [], None: []}
    for r in rows:
        buckets.setdefault(r["importance"], []).append(dict(r))
    return buckets


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    topics = cfg["topics"]

    rows = db.fetch_items(topic=TOPIC, since_hours=HOURS, limit=1000)
    grouped = group_by_importance(rows)
    daily = db.daily_counts(days=14)
    topic_cnt = db.topic_counts(since_hours=HOURS)
    last = db.last_run()
    last_dict = dict(last) if last else None
    today = (last_dict["finished_at"] or last_dict["started_at"]) if last_dict else ""
    total_today = sum(n for d, n in daily if d == datetime.utcnow().strftime("%Y-%m-%d"))

    css = CSS_FILE.read_text()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("index.html")
    html = template.render(
        mode="export",
        inline_css=css,
        topics=["All"] + topics,
        active_topic=TOPIC,
        hours=HOURS,
        grouped=grouped,
        daily=daily,
        topic_cnt=topic_cnt,
        last_run=last_dict,
        total_today=total_today,
    )

    OUT_FILE.write_text(html, encoding="utf-8")
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"Wrote {OUT_FILE} ({size_kb:.1f} KB)")
    print(f"  · {sum(len(v) for v in grouped.values())} items, last {HOURS}h, topic={TOPIC}")
    print(f"  · open with:  open {OUT_FILE}")


if __name__ == "__main__":
    main()
