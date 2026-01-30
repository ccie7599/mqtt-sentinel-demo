#!/bin/bash
# Create Linode VMs for distributed load testing
#
# Usage: ./create_workers.sh [count]
#   count: Number of worker VMs to create (default: 4)

set -e

WORKER_COUNT=${1:-4}
REGION="us-east"
INSTANCE_TYPE="g6-dedicated-16"
IMAGE="linode/ubuntu24.04"
LABEL_PREFIX="locust-worker"
ROOT_PASS=$(openssl rand -base64 24)
SSH_KEY_FILE="$HOME/.ssh/id_rsa.pub"

# Target NATS leaf node
MQTT_TARGET_IP="198.74.59.108"
MQTT_TARGET_PORT="443"

echo "============================================================"
echo "Creating $WORKER_COUNT Locust Worker VMs"
echo "============================================================"
echo "Region: $REGION"
echo "Instance Type: $INSTANCE_TYPE"
echo "Target: $MQTT_TARGET_IP:$MQTT_TARGET_PORT"
echo "============================================================"

# Check if SSH key exists
if [ ! -f "$SSH_KEY_FILE" ]; then
    echo "Error: SSH public key not found at $SSH_KEY_FILE"
    echo "Generate one with: ssh-keygen -t rsa -b 4096"
    exit 1
fi

SSH_KEY=$(cat "$SSH_KEY_FILE")

# Store worker IPs
WORKER_IPS=()

# Create workers
for i in $(seq 1 $WORKER_COUNT); do
    LABEL="${LABEL_PREFIX}-${i}"
    echo ""
    echo "Creating $LABEL..."

    # Create the instance
    RESULT=$(linode-cli linodes create \
        --label "$LABEL" \
        --region "$REGION" \
        --type "$INSTANCE_TYPE" \
        --image "$IMAGE" \
        --root_pass "$ROOT_PASS" \
        --authorized_keys "$SSH_KEY" \
        --json)

    LINODE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
    echo "  Created Linode ID: $LINODE_ID"

    # Wait for the instance to be running
    echo "  Waiting for instance to be running..."
    while true; do
        STATUS=$(linode-cli linodes view "$LINODE_ID" --json | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['status'])")
        if [ "$STATUS" = "running" ]; then
            break
        fi
        sleep 5
    done

    # Get the IP
    IP=$(linode-cli linodes view "$LINODE_ID" --json | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['ipv4'][0])")
    WORKER_IPS+=("$IP")
    echo "  IP: $IP"
done

echo ""
echo "============================================================"
echo "Workers Created"
echo "============================================================"
echo "Root Password: $ROOT_PASS"
echo ""
echo "Worker IPs:"
for i in "${!WORKER_IPS[@]}"; do
    echo "  worker-$((i+1)): ${WORKER_IPS[$i]}"
done

# Save worker info to file
cat > workers.env << EOF
# Locust Worker Configuration
# Generated: $(date)
MQTT_TARGET_IP=$MQTT_TARGET_IP
MQTT_TARGET_PORT=$MQTT_TARGET_PORT
ROOT_PASS=$ROOT_PASS
WORKER_COUNT=$WORKER_COUNT
WORKER_IPS=(${WORKER_IPS[@]})
EOF

echo ""
echo "Worker info saved to workers.env"
echo ""
echo "Next steps:"
echo "  1. Wait ~60s for VMs to finish booting"
echo "  2. Run: ./setup_workers.sh"
echo "  3. Run: ./run_distributed_test.sh"
