#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

command -v python3 >/dev/null 2>&1 || {
  echo "[ERROR] Python 3.9+ is required before installing project dependencies." >&2
  exit 1
}
command -v node >/dev/null 2>&1 || {
  echo "[ERROR] Node.js 20.19+ or 22.12+ is required before installing project dependencies." >&2
  exit 1
}
command -v npm >/dev/null 2>&1 || {
  echo "[ERROR] npm is required before installing project dependencies." >&2
  exit 1
}

python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" || {
  echo "[ERROR] Python 3.9+ is required." >&2
  exit 1
}
node -e "const [a,b]=process.versions.node.split('.').map(Number);if(!((a===20&&b>=19)||(a>=22&&(a>22||b>=12)))){console.error('[ERROR] Node.js 20.19+ or 22.12+ is required.');process.exit(1)}"

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating Python virtual environment in .venv..."
  python3 -m venv .venv || {
    echo "[ERROR] Could not create .venv. On Debian/Ubuntu, install python3-venv first." >&2
    exit 1
  }
fi

rm -f .venv/.course-agent-deps-ready

echo "Installing Python dependencies from requirements.txt..."
.venv/bin/python -m pip install -r requirements.txt

echo "Installing locked frontend dependencies from frontend/package-lock.json..."
npm ci --prefix frontend --include=dev

touch .venv/.course-agent-deps-ready

echo "All project dependencies are installed. Run ./start.sh to start the application."
