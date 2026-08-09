#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Local/dev default 127.0.0.1; server deploy uses deploy/install.sh → 0.0.0.0:8080
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  PY=python3
  "$PY" -m pip install -r requirements.txt
fi
exec "$PY" web.py --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"
