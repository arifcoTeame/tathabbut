#!/usr/bin/env bash
# One-shot local setup: venv + deps + index + tests.   Usage:  ./setup.sh   (or ./setup.sh bge-m3)
set -euo pipefail
cd "$(dirname "$0")"
EMBEDDER="${1:-tfidf-char}"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
if [ "$EMBEDDER" = "bge-m3" ]; then
  python -m pip install --quiet torch --index-url https://download.pytorch.org/whl/cpu
  python -m pip install --quiet -r requirements-bge.txt
fi
python scripts/build_index.py --embedder "$EMBEDDER"
python -m pytest -q
echo
echo "Ready. Start the API with:"
echo "  source .venv/bin/activate && uvicorn app.main:app --reload --port 8000"
