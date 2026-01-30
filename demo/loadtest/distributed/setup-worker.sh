#!/bin/bash
# Locust Worker Setup for Linode VMs
# Run this on each worker VM in us-east region

set -e

# Install dependencies
apt-get update
apt-get install -y python3 python3-pip python3-venv git

# Clone the demo repo
cd /opt
git clone https://github.com/ccie7599/mqtt-sentinel-demo.git || true
cd mqtt-sentinel-demo/demo/loadtest

# Create venv and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install locust paho-mqtt pyyaml

# Update config to use internal cluster DNS or direct IPs
cat > config.yaml << 'EOF'
mqtt_broker: "mqtt.connected-cloud.io"
mqtt_port: 30883
use_tls: true
user_max: 50000
topic_pattern: "clients/{client_id}/alerts"
keepalive: 60
reconnect_delay: 5
connect_timeout: 10
subscribe_timeout: 5
EOF

echo "Setup complete. Run worker with:"
echo "  source venv/bin/activate"
echo "  locust -f locustfile.py --worker --master-host=<MASTER_IP>"
