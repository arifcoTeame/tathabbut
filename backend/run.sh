#!/usr/bin/env bash
# Works from ANY folder: always switches to backend/ and uses its .venv.
#   bash run.sh build   -> rebuild the index
#   bash run.sh test    -> run the tests
#   bash run.sh serve   -> start the API on http://localhost:8000
#   bash run.sh all     -> build + test + serve
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || { echo "No .venv yet - running setup.sh first"; bash setup.sh; }
source .venv/bin/activate

case "${1:-all}" in
  build) python scripts/build_index.py "${@:2}" ;;
  test)  python -m pytest -q ;;
  serve) uvicorn app.main:app --reload --port 8000 ;;
  all)   python scripts/build_index.py && python -m pytest -q && uvicorn app.main:app --reload --port 8000 ;;
  *)     echo "usage: bash run.sh [build|test|serve|all]"; exit 1 ;;
esac
