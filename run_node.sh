#!/bin/bash
# Script to run a single node
echo "Starting a Peoples Coin node..."

# Navigate to the project root (if script is run from parent directory)
# cd "$(dirname "$0")"

# Activate the virtual environment
source venv/bin/activate

# Run your main application file
python run.py # Or 'python ambient_node.py' or specific Flask command

echo "Node stopped."
