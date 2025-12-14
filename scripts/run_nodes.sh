#!/bin/bash
# Script to run multiple nodes in the background

echo "Starting multiple Peoples Coin nodes..."

# Example: Run 3 nodes
for i in $(seq 1 3); do
    echo "Starting node $i..."
    # Run in background. Adjust command based on how you start your node.
    # You might need to pass arguments for unique node IDs/ports.
    # ./run_node.sh $i &
    python run.py --node-id $i & # Example for a Python app that takes args
    sleep 1 # Give a moment for it to start
done

echo "All nodes launched in background."
echo "Use 'jobs' to see background processes, 'fg %<job_num>' to bring to foreground, 'kill %<job_num>' to stop."
