"""One-shot backward scan — temporarily bumps lookback + per-source caps,
runs the full pipeline, then exits. Existing items dedupe by URL so this
is safe to run repeatedly. Useful when:
  - You suspect missed updates after a system sleep / network outage
  - You just added new sources and want to backfill history
  - You want to deepen the arXiv / Bluesky / Reddit window

Usage:
    python scripts/backward_scan.py [hours] [max_per_source]
    python scripts/backward_scan.py 168 100      # 1 week, 100 items/source
    python scripts/backward_scan.py 720 200      # 30 days, 200 items/source
Defaults: 168h, 100 items/source.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)

import scheduler  # noqa: E402

hours = int(sys.argv[1]) if len(sys.argv) > 1 else 168
max_per = int(sys.argv[2]) if len(sys.argv) > 2 else 100

# Monkey-patch config loader so this run uses bigger windows without
# touching config.yaml on disk.
_orig = scheduler.load_config


def patched():
    cfg = _orig()
    cfg["lookback_hours"] = hours
    cfg["max_items_per_source"] = max_per
    return cfg


scheduler.load_config = patched

print(f"Backward scan: lookback={hours}h, max_per_source={max_per}")
scheduler.run()
print("Done.")
