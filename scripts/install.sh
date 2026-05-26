#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "==> Syncing dependencies with uv"
uv sync

echo "==> Initializing DB"
uv run python -c "from storage import db; db.init_db(); print('DB ready at', db.DB_PATH)"

echo "==> Done. Next steps:"
echo "   1. Run one-shot collection:    uv run python scheduler.py"
echo "   2. Start the web UI:           uv run uvicorn web.app:app --host 127.0.0.1 --port 8765"
echo "   3. Install launchd 12h job:    bash scripts/install_launchd.sh"
