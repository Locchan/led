#!/usr/bin/env bash
# Create a local virtualenv, install this project (and its dependencies) into
# it, and run the test suite against the working tree.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required but was not found on PATH." >&2
    exit 1
fi

if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    echo "ERROR: python3 -m venv is not fully usable (the 'venv' or 'ensurepip' module is missing)." >&2
    exit 1
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
    echo "Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies into $VENV_DIR..."
"$VENV_DIR/bin/pip" install --quiet -e "$SCRIPT_DIR"

echo "Running tests..."
cd "$SCRIPT_DIR"
exec "$VENV_DIR/bin/python" -m unittest discover -s tests -v -b
