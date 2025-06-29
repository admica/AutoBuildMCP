#!/bin/bash
set -euo pipefail

YELLOW='\033[1;33m'
RED='\033[1;31m'
NC='\033[0m' # No Color

VENV_PATH="venv/bin/activate"
if [ ! -f "$VENV_PATH" ]; then
    echo -e "${RED}Error: Virtual environment not found at $VENV_PATH.${NC}"
    exit 1
fi

echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_PATH"

if ! command -v pip > /dev/null; then
    echo -e "${RED}Error: pip not found in virtual environment.${NC}"
    exit 1
fi

if [ ! -f "server.py" ]; then
    echo -e "${RED}Error: server.py not found in current directory.${NC}"
    exit 1
fi

export MCP_PORT=${MCP_PORT:-5305}
echo -e "${YELLOW}Starting AutoBuildMCP server on http://localhost:$MCP_PORT...${NC}"
venv/bin/uvicorn server:app --host 0.0.0.0 --port "$MCP_PORT"
