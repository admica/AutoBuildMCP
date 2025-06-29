#!/bin/bash
set -euo pipefail

VENV_PATH="venv/bin/activate"
if [ ! -f "$VENV_PATH" ]; then
    echo "Virtual environment not found at $VENV_PATH"
    exit 1
fi

source "$VENV_PATH"
mcp run server.py
