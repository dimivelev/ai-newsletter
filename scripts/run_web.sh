#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run uvicorn web.app:app --host 127.0.0.1 --port 8765 --reload
