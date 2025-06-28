#!/bin/bash

# Colors
YELLOW='\033[1;33m'
RED='\033[1;31m'
NC='\033[0m' # No Color

# --- Activate Virtual Environment ---
VENV_PATH="venv/bin/activate"
if [ ! -f "$VENV_PATH" ]; then
    echo -e "${RED}Error: Virtual environment not found at $VENV_PATH.${NC}"
    exit 1
fi

echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_PATH" || exit 1

# --- Check for required file ---
if [ ! -f "server.py" ]; then
    echo -e "${RED}Error: server.py not found in current directory.${NC}"
    exit 1
fi

# --- Ensure sse-starlette is installed ---
if ! pip show sse-starlette > /dev/null 2>&1; then
    echo -e "${YELLOW}sse-starlette not found. Installing...${NC}"
    pip install sse-starlette
fi

# --- Set Default Port ---
export MCP_PORT=${MCP_PORT:-5501}

# --- Start Server ---
echo -e "${YELLOW}Starting AutoBuildMCP server on port $MCP_PORT...${NC}"
venv/bin/python server.py >> server.log 2>&1 &

# --- Wait Briefly and Check if Server Started ---
sleep 2
if ! pgrep -f "python server.py" > /dev/null; then
    echo -e "${RED}Error: Server failed to start. Check server.log for details.${NC}"
    exit 1
else
    echo -e "${YELLOW}Server started successfully. Logs are in server.log.${NC}"
fi
