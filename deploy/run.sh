#!/usr/bin/env bash
# Windows-friendly deploy script (Git Bash / WSL / MSYS).
# From repo root or deploy/: clears caches, creates .venv, installs deps, runs the API.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

echo "============================================"
echo " API Aggregation Platform - Deploy"
echo "============================================"
echo " Project root: ${ROOT_DIR}"
echo

echo "[1/4] Clearing Python caches..."
find . -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) \
  -not -path './.venv/*' -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f -name '*.pyc' -not -path './.venv/*' -delete 2>/dev/null || true
rm -f .coverage 2>/dev/null || true
echo "      Done."

echo "[2/4] Creating virtual environment (.venv)..."
if [[ -x ".venv/Scripts/python.exe" ]]; then
  PYTHON=".venv/Scripts/python.exe"
  echo "      .venv already exists (Windows) - reusing it."
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
  echo "      .venv already exists (Unix) - reusing it."
else
  if command -v py >/dev/null 2>&1; then
    py -3 -m venv .venv
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
  else
    python -m venv .venv
  fi

  if [[ -x ".venv/Scripts/python.exe" ]]; then
    PYTHON=".venv/Scripts/python.exe"
  else
    PYTHON=".venv/bin/python"
  fi
  echo "      Created .venv"
fi

echo "[3/4] Installing dependencies..."
"${PYTHON}" -m pip install --upgrade pip
"${PYTHON}" -m pip install -r requirements.txt

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
  echo "      Created .env from .env.example"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "[4/4] Starting API on http://127.0.0.1:${PORT} ..."
echo "      Admin:  http://127.0.0.1:${PORT}/admin"
echo "      Docs:   http://127.0.0.1:${PORT}/docs"
echo "      Press Ctrl+C to stop."
echo
exec "${PYTHON}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" --reload
