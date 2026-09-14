#!/bin/bash
set -e
cd "$(dirname "$0")"
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python 3 is required. Install it from python.org, then run this file again."
  read -r -p "Press Enter to close..."
  exit 1
fi
"$PYTHON_BIN" start.py
STATUS=$?
if [ "$STATUS" -ne 0 ]; then
  echo "EventFlow exited with status $STATUS."
  read -r -p "Press Enter to close..."
fi
