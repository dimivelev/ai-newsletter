#!/usr/bin/env python3
"""CLI script to export AI News Tracker summaries as digests.

Usage:
    python scripts/export_digest.py --hours 24 --format both
    python scripts/export_digest.py --hours 168 --topic "Frontier Models" --min-importance 3
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import storage.db as db
from storage import exporter

def main() -> None:
    # Initialize DB (creates bookmarks schema if missing)
    db.init_db()

    parser = argparse.ArgumentParser(description="Export daily/weekly AI news digests.")
    parser.add_argument(
        "--hours",
        type=int,
        default=168,
        help="Lookback period in hours (e.g. 24 for daily, 168 for weekly. Default: 168)",
    )
    parser.add_argument(
        "--min-importance",
        type=int,
        default=2,
        help="Minimum importance level (1=routine, 2=notable, 3=major. Default: 2)",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="All",
        help="Topic category filter (Default: All)",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "html", "both"],
        default="both",
        help="Output file format (Default: both)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="export",
        help="Directory to save exported digests (Default: export)",
    )

    args = parser.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(exist_ok=True)
    
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    print(f"Generating news digest (last {args.hours}h, topic={args.topic}, min_importance={args.min_importance})...")

    if args.format in ("markdown", "both"):
        md = exporter.generate_markdown_digest(
            since_hours=args.hours,
            min_importance=args.min_importance,
            topic=args.topic,
        )
        md_file = out_dir / f"digest_{date_str}.md"
        md_file.write_text(md, encoding="utf-8")
        print(f"Wrote Markdown digest to {md_file}")

    if args.format in ("html", "both"):
        html = exporter.generate_html_digest(
            since_hours=args.hours,
            min_importance=args.min_importance,
            topic=args.topic,
        )
        html_file = out_dir / f"digest_{date_str}.html"
        html_file.write_text(html, encoding="utf-8")
        print(f"Wrote HTML digest to {html_file}")

if __name__ == "__main__":
    main()
