#!/bin/bash

# Exit on error
set -e

# Colors
CYAN='\033[1;34m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# --- Create Virtual Environment ---
echo -e "${CYAN}Creating Virtual Environment...${NC}"
if [ ! -d "venv" ]; then
  python3 -m venv venv
  echo "Virtual environment 'venv' created."
else
  echo "Virtual environment 'venv' already exists."
fi

# --- Activate Virtual Environment ---
source venv/bin/activate

# --- Upgrade Pip ---
echo -e "\n${CYAN}Upgrading Pip...${NC}"
python -m pip install --upgrade pip

# --- Install Dependencies ---
if [ -f "requirements.txt" ]; then
  echo -e "\n${CYAN}Installing Dependencies from requirements.txt...${NC}"
  pip install -r requirements.txt
else
  echo -e "\n${CYAN}Skipping Dependency Installation (requirements.txt not found).${NC}"
fi

echo -e "\n${GREEN}Build process complete. Environment is ready.${NC}"
