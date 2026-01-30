#!/bin/bash
# Stop distributed Locust load test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load worker configuration
if [ ! -f "$SCRIPT_DIR/workers.env" ]; then
    echo "Error: workers.env not found."
    exit 1
fi
source "$SCRIPT_DIR/workers.env"

echo "Stopping distributed load test..."

for i in "${!WORKER_IPS[@]}"; do
    IP="${WORKER_IPS[$i]}"
    echo "  Stopping on $IP..."
    ssh -o StrictHostKeyChecking=no root@$IP "pkill -f locust || true" 2>/dev/null || true
done

echo "All workers stopped."
