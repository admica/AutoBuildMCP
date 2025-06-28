#!/bin/bash
set -euo pipefail

# Colors
CYAN='\033[1;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}Starting build environment setup...${NC}"

# Cleanup Python env vars that can interfere
echo -e "${CYAN}Cleaning Python environment variables...${NC}"
unset VIRTUAL_ENV || true
unset PYTHONHOME || true
unset PYTHONPATH || true

# Clean PATH from old venv bins
echo -e "${CYAN}Cleaning PATH environment variable...${NC}"
IFS=':' read -r -a path_array <<< "$PATH"
clean_path=""
for p in "${path_array[@]}"; do
    if [[ "$p" != *"/venv/bin"* ]]; then
        clean_path+="$p:"
    fi
done
clean_path="${clean_path%:}"
export PATH="$clean_path"

# Check for python3
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Error: python3 command not found. Please install Python 3.${NC}" >&2
    exit 10
fi

# Remove old venv if exists
if [ -d "venv" ]; then
    echo -e "${CYAN}Removing existing 'venv' directory...${NC}"
    rm -rf venv
    echo "Removed existing virtual environment."
fi

# Try to create venv
echo -e "${CYAN}Creating a new virtual environment with python3 -m venv...${NC}"
if python3 -m venv venv; then
    echo "Virtual environment created successfully."
else
    echo -e "${CYAN}python3 -m venv failed. Trying fallback with virtualenv...${NC}"

    # Check if virtualenv installed
    if ! command -v virtualenv &>/dev/null; then
        echo -e "${RED}virtualenv is not installed.${NC}"
        echo -e "${CYAN}Attempting to install virtualenv globally... (requires sudo)${NC}"
        if command -v pip3 &>/dev/null; then
            sudo pip3 install virtualenv
        else
            echo -e "${RED}pip3 not found to install virtualenv. Please install python3-venv or virtualenv manually.${NC}"
            exit 20
        fi
    fi

    # Retry creating venv with virtualenv
    if virtualenv venv; then
        echo "Virtual environment created successfully using virtualenv."
    else
        echo -e "${RED}Failed to create virtual environment with virtualenv.${NC}"
        exit 30
    fi
fi

# Activate venv
echo -e "${CYAN}Activating virtual environment...${NC}"
# shellcheck disable=SC1091
source venv/bin/activate

# Upgrade pip/setuptools/wheel
echo -e "${CYAN}Upgrading pip, setuptools, and wheel...${NC}"
pip install --upgrade pip setuptools wheel

# Install dependencies if requirements.txt present
if [ -f "requirements.txt" ]; then
    echo -e "${CYAN}Installing dependencies from requirements.txt...${NC}"
    pip install -r requirements.txt
else
    echo -e "${CYAN}No requirements.txt found, skipping dependency installation.${NC}"
fi

echo -e "${GREEN}Build environment setup complete and ready!${NC}"

