import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import db

TEMPLATE_DIR = ROOT / "web" / "templates"
env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _get_and_group_items(since_hours: int, min_importance: int, topic: str,
                         q: Optional[str] = None,
                         sources: Optional[list[str]] = None) -> dict[int, list[dict]]:
    if topic == "Bookmarked":
        rows = db.fetch_bookmarked_items(q=q, sources=sources)
    else:
        rows = db.fetch_items(topic=topic, since_hours=since_hours, limit=1000, q=q, sources=sources)
    
    # Group items by importance
    # Buckets: 3 (Major), 2 (Notable), 1 (Routine)
    buckets = {3: [], 2: [], 1: []}
    for r in rows:
        item = dict(r)
        imp = item.get("importance")
        if imp is None:
            imp = 1
        
        if imp >= min_importance:
            buckets.setdefault(imp, []).append(item)
            
    return buckets


def generate_markdown_digest(since_hours: int = 168, min_importance: int = 2,
                             topic: str = "All", q: Optional[str] = None,
                             sources: Optional[list[str]] = None) -> str:
    buckets = _get_and_group_items(since_hours, min_importance, topic, q, sources)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    
    lines = []
    lines.append(f"# The AI Dispatch - News Digest")
    lines.append(f"Generated on {now} UTC  ")
    lines.append(f"Parameters: Lookback={since_hours}h | Topic={topic} | Min Importance={min_importance}")
    if q:
        lines.append(f"Search Query: \"{q}\"  ")
    if sources:
        lines.append(f"Sources Filter: {', '.join(sources)}  ")
    lines.append("")
    
    # 3 = Major, 2 = Notable, 1 = Routine
    labels = {
        3: "🔥 Major Announcements",
        2: "⭐ Notable News",
        1: "📰 Routine Updates"
    }
    
    total_items = 0
    for level in [3, 2, 1]:
        items = buckets.get(level, [])
        if not items:
            continue
        total_items += len(items)
        lines.append(f"## {labels[level]} ({len(items)})")
        lines.append("")
        
        for idx, it in enumerate(items, 1):
            pub_date = it['published_at'][:10]
            lines.append(f"### {idx}. [{it['title']}]({it['url']})")
            lines.append(f"*Source: **{it['source']}** ({it['source_type']}) · Published: {pub_date}*")
            if it.get('tldr'):
                lines.append(f"> **TL;DR:** {it['tldr']}")
            if it.get('importance_why'):
                lines.append(f"**Why it matters:** {it['importance_why']}  ")
            lines.append("")
            
    if total_items == 0:
        lines.append("*— No items found matching the filter criteria —*")
        
    return "\n".join(lines)


def generate_html_digest(since_hours: int = 168, min_importance: int = 2,
                          topic: str = "All", q: Optional[str] = None,
                          sources: Optional[list[str]] = None) -> str:
    buckets = _get_and_group_items(since_hours, min_importance, topic, q, sources)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    
    template = env.get_template("digest_template.html")
    return template.render(
        now=now,
        since_hours=since_hours,
        topic=topic,
        q=q,
        sources=sources,
        min_importance=min_importance,
        grouped=buckets,
        total_items=sum(len(items) for items in buckets.values())
    )
