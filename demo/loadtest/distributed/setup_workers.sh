#!/bin/bash
# Setup Locust workers on remote VMs
#
# Usage: ./setup_workers.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOADTEST_DIR="$(dirname "$SCRIPT_DIR")"

# Load worker configuration
if [ ! -f "$SCRIPT_DIR/workers.env" ]; then
    echo "Error: workers.env not found. Run create_workers.sh first."
    exit 1
fi
source "$SCRIPT_DIR/workers.env"

echo "============================================================"
echo "Setting up ${#WORKER_IPS[@]} Locust Workers"
echo "============================================================"

# Files to copy
FILES_TO_COPY=(
    "$LOADTEST_DIR/locustfile_distributed.py"
    "$LOADTEST_DIR/requirements.txt"
)

SETUP_SCRIPT='#!/bin/bash
set -e

# Update system
apt-get update
apt-get install -y python3-pip python3-venv

# Increase file descriptor limits
cat >> /etc/security/limits.conf << EOF
* soft nofile 1000000
* hard nofile 1000000
root soft nofile 1000000
root hard nofile 1000000
EOF

# Increase socket buffer sizes and connection limits
cat >> /etc/sysctl.conf << EOF
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_fin_timeout = 15
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
fs.file-max = 2000000
EOF
sysctl -p

# Create work directory
mkdir -p /opt/locust
cd /opt/locust

# Setup Python venv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Setup complete!"
'

for i in "${!WORKER_IPS[@]}"; do
    IP="${WORKER_IPS[$i]}"
    WORKER_NUM=$((i + 1))
    echo ""
    echo "Setting up worker-$WORKER_NUM ($IP)..."

    # Wait for SSH to be available
    echo "  Waiting for SSH..."
    for attempt in {1..30}; do
        if ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@$IP "echo ok" &>/dev/null; then
            break
        fi
        sleep 5
    done

    # Copy files
    echo "  Copying files..."
    scp -o StrictHostKeyChecking=no "${FILES_TO_COPY[@]}" root@$IP:/tmp/

    # Run setup
    echo "  Running setup script..."
    ssh -o StrictHostKeyChecking=no root@$IP "
        mv /tmp/locustfile_distributed.py /opt/locust/ 2>/dev/null || mkdir -p /opt/locust && mv /tmp/locustfile_distributed.py /opt/locust/
        mv /tmp/requirements.txt /opt/locust/
        $SETUP_SCRIPT
    "

    echo "  Worker-$WORKER_NUM setup complete!"
done

echo ""
echo "============================================================"
echo "All workers configured!"
echo "============================================================"
echo ""
echo "To run the distributed test:"
echo "  ./run_distributed_test.sh --users 40000 --spawn-rate 200"
