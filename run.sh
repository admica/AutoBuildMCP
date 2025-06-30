#!/bin/bash
set -euo pipefail

# Change to the script's directory to ensure relative paths work correctly
cd "$(dirname "$0")"

VENV_PATH="venv/bin/activate"
if [ ! -f "$VENV_PATH" ]; then
    echo "Virtual environment not found at $VENV_PATH"
    exit 1
fi

source "$VENV_PATH"
python server.py
