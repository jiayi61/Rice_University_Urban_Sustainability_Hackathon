#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  exec python3 -m uvicorn app.main:app --reload --port "${PORT:-8000}"
fi
exec python3 start.py --port "${PORT:-8000}"
