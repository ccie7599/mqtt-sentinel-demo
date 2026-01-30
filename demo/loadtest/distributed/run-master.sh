#!/bin/bash
# Run Locust master (can run locally or on a VM)
# Workers connect to this master to receive work

WORKERS=${1:-4}
USERS=${2:-10000}
SPAWN_RATE=${3:-500}
RUN_TIME=${4:-300}

echo "Starting Locust master"
echo "  Expected workers: $WORKERS"
echo "  Users: $USERS"
echo "  Spawn rate: $SPAWN_RATE/sec"
echo "  Run time: ${RUN_TIME}s"
echo ""
echo "Web UI: http://localhost:8089"
echo ""

cd "$(dirname "$0")/.."
source ../venv/bin/activate 2>/dev/null || source venv/bin/activate

locust -f locustfile.py \
  --master \
  --expect-workers=$WORKERS \
  --users=$USERS \
  --spawn-rate=$SPAWN_RATE \
  --run-time=${RUN_TIME}s \
  --web-host=0.0.0.0
