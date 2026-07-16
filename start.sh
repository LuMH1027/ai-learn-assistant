#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

command -v node >/dev/null 2>&1 || { echo "[ERROR] Node.js 20.19+ or 22.12+ is required." >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "[ERROR] npm is required." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "[ERROR] Python 3.9+ is required." >&2; exit 1; }

node -e "const [a,b]=process.versions.node.split('.').map(Number);if(!((a===20&&b>=19)||(a>=22&&(a>22||b>=12)))){console.error('[ERROR] Node.js 20.19+ or 22.12+ is required.');process.exit(1)}"
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" || { echo "[ERROR] Python 3.9+ is required." >&2; exit 1; }

if [[ ! -d frontend/node_modules ]]; then
  echo "Installing frontend dependencies..."
  npm ci --prefix frontend
fi

echo "Building Vue frontend..."
npm run build --prefix frontend

echo "Starting Local Course Agent at http://127.0.0.1:8000"
exec python3 run.py
