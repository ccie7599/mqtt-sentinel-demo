#!/bin/bash
# Run distributed Locust load test
#
# Usage: ./run_distributed_test.sh [options]
#   --users         Total number of users (default: 40000)
#   --spawn-rate    Users to spawn per second (default: 200)
#   --duration      Test duration (default: 300s)
#   --target-ip     MQTT broker IP (default: from workers.env)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default values
TOTAL_USERS=40000
SPAWN_RATE=200
DURATION="300s"
TARGET_IP=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --users)
            TOTAL_USERS="$2"
            shift 2
            ;;
        --spawn-rate)
            SPAWN_RATE="$2"
            shift 2
            ;;
        --duration)
            DURATION="$2"
            shift 2
            ;;
        --target-ip)
            TARGET_IP="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Load worker configuration
if [ ! -f "$SCRIPT_DIR/workers.env" ]; then
    echo "Error: workers.env not found. Run create_workers.sh first."
    exit 1
fi
source "$SCRIPT_DIR/workers.env"

# Use target IP from env if not specified
if [ -z "$TARGET_IP" ]; then
    TARGET_IP="$MQTT_TARGET_IP"
fi

WORKER_COUNT=${#WORKER_IPS[@]}
USERS_PER_WORKER=$((TOTAL_USERS / WORKER_COUNT))
SPAWN_RATE_PER_WORKER=$((SPAWN_RATE / WORKER_COUNT))

echo "============================================================"
echo "Distributed MQTT Load Test"
echo "============================================================"
echo "Target: mqtts://$TARGET_IP:$MQTT_TARGET_PORT"
echo "Total Users: $TOTAL_USERS"
echo "Spawn Rate: $SPAWN_RATE/sec"
echo "Duration: $DURATION"
echo "Workers: $WORKER_COUNT"
echo "Users per Worker: $USERS_PER_WORKER"
echo "============================================================"
echo ""

# Use first worker as master
MASTER_IP="${WORKER_IPS[0]}"
echo "Master node: $MASTER_IP"
echo ""

# Start master on first worker
echo "Starting master on $MASTER_IP..."
ssh -o StrictHostKeyChecking=no root@$MASTER_IP "
    cd /opt/locust
    source venv/bin/activate

    # Set environment
    export WORKER_INDEX=0
    export WORKER_COUNT=$WORKER_COUNT
    export MQTT_BROKER=$TARGET_IP
    export MQTT_PORT=$MQTT_TARGET_PORT

    # Start master (also acts as worker 0)
    nohup locust -f locustfile_distributed.py \
        --master \
        --expect-workers=$((WORKER_COUNT - 1)) \
        --host=mqtts://$TARGET_IP:$MQTT_TARGET_PORT \
        --headless \
        -u $TOTAL_USERS \
        -r $SPAWN_RATE \
        -t $DURATION \
        > /var/log/locust-master.log 2>&1 &

    echo \$! > /var/run/locust-master.pid
    echo 'Master started with PID:' \$(cat /var/run/locust-master.pid)
"

# Give master time to start
sleep 5

# Start workers on remaining nodes
for i in $(seq 1 $((WORKER_COUNT - 1))); do
    WORKER_IP="${WORKER_IPS[$i]}"
    echo "Starting worker $i on $WORKER_IP..."

    ssh -o StrictHostKeyChecking=no root@$WORKER_IP "
        cd /opt/locust
        source venv/bin/activate

        # Set environment for this worker
        export WORKER_INDEX=$i
        export WORKER_COUNT=$WORKER_COUNT
        export MQTT_BROKER=$TARGET_IP
        export MQTT_PORT=$MQTT_TARGET_PORT

        # Start worker
        nohup locust -f locustfile_distributed.py \
            --worker \
            --master-host=$MASTER_IP \
            > /var/log/locust-worker.log 2>&1 &

        echo \$! > /var/run/locust-worker.pid
        echo 'Worker started with PID:' \$(cat /var/run/locust-worker.pid)
    "
done

echo ""
echo "============================================================"
echo "Distributed test started!"
echo "============================================================"
echo ""
echo "Monitor master logs:"
echo "  ssh root@$MASTER_IP 'tail -f /var/log/locust-master.log'"
echo ""
echo "Monitor Prometheus metrics:"
echo "  kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring"
echo "  Open: http://localhost:3000/d/mqtt-security-overview"
echo ""
echo "Stop test:"
echo "  ./stop_distributed_test.sh"
