#!/bin/bash
# Run Locust worker - connects to master
# Usage: ./run-worker.sh <MASTER_IP>

MASTER_HOST=${1:-localhost}

cd "$(dirname "$0")/.."
source venv/bin/activate

echo "Starting Locust worker, connecting to master at $MASTER_HOST"
locust -f locustfile.py --worker --master-host=$MASTER_HOST
