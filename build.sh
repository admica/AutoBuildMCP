#!/bin/bash

# Exit on error
set -e

# Create virtual environment
if [ ! -d "venv" ]; then
  echo "Creating virtual environment 'venv'..."
  python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

echo "Virtual environment activated."

# Install dependencies from requirements.txt if it exists
if [ -f "requirements.txt" ]; then
  echo "Installing requirements from requirements.txt..."
  pip install -r requirements.txt
else
  echo "No requirements.txt file found. Skipping dependency installation."
fi

echo "Build process complete."
