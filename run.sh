#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/python" ]; then
    exec .venv/bin/python main.py "$@"
elif command -v uv &> /dev/null; then
    exec uv run python main.py "$@"
else
    exec python3 main.py "$@"
fi
