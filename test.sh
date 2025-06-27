#!/bin/bash

# Activate the virtual environment
source ./venv/bin/activate

# Run all Python files in the test directory
cd test
for f in *.py; do
    python "$f"
done
