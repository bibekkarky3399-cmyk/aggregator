#!/usr/bin/env bash
# macOS deploy script: clear caches, create .venv, install deps, run the API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

echo "============================================"
echo " API Aggregation Platform - macOS Deploy"
echo "============================================"
echo " Project root: ${ROOT_DIR}"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install Python 3 (e.g. brew install python)."
  exit 1
fi

echo "[1/4] Clearing Python caches..."
find . -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) \
  -not -path './.venv/*' -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
find . -type f -name '*.pyc' -not -path './.venv/*' -delete 2>/dev/null || true
rm -f .coverage 2>/dev/null || true
echo "      Done."

echo "[2/4] Creating virtual environment (.venv)..."
if [[ -x ".venv/bin/python" ]]; then
  echo "      .venv already exists - reusing it."
else
  python3 -m venv .venv
  echo "      Created .venv"
fi
PYTHON="${ROOT_DIR}/.venv/bin/python"

echo "[3/4] Installing dependencies..."
"${PYTHON}" -m pip install --upgrade pip
"${PYTHON}" -m pip install -r requirements.txt

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
  echo "      Created .env from .env.example"
fi

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "[4/4] Starting API on http://${HOST}:${PORT} ..."
echo "      Admin:  http://${HOST}:${PORT}/admin"
echo "      Docs:   http://${HOST}:${PORT}/docs"
echo "      Press Ctrl+C to stop."
echo
exec "${PYTHON}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
