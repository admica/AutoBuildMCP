#!/bin/bash

# Colors
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --- Activate Virtual Environment ---
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# --- Start Server ---
echo -e "${YELLOW}Starting AutoBuildMCP server...${NC}"
python server.py
