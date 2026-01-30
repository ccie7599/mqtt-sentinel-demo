#!/bin/bash
# Provision Locust worker VMs on Linode using CLI
# Requires: linode-cli configured with API token

NUM_WORKERS=${1:-4}
REGION="us-east"
TYPE="g6-dedicated-4"  # 4 vCPU, 8GB - good for load testing
IMAGE="linode/debian12"
LABEL_PREFIX="locust-worker"

echo "Provisioning $NUM_WORKERS Locust workers in $REGION..."

WORKER_IPS=""

for i in $(seq 1 $NUM_WORKERS); do
  LABEL="${LABEL_PREFIX}-${i}"
  echo "Creating $LABEL..."

  # Create Linode with setup script
  RESULT=$(linode-cli linodes create \
    --label "$LABEL" \
    --region "$REGION" \
    --type "$TYPE" \
    --image "$IMAGE" \
    --root_pass "$(openssl rand -base64 24)" \
    --tags locust-loadtest \
    --json)

  IP=$(echo "$RESULT" | jq -r '.[0].ipv4[0]')
  ID=$(echo "$RESULT" | jq -r '.[0].id')

  echo "  Created: $LABEL (ID: $ID, IP: $IP)"
  WORKER_IPS="$WORKER_IPS $IP"
done

echo ""
echo "=== Workers Created ==="
echo "IPs:$WORKER_IPS"
echo ""
echo "Wait ~2 minutes for boot, then run on each worker:"
echo ""
echo "  ssh root@<IP>"
echo "  curl -sL https://raw.githubusercontent.com/ccie7599/mqtt-sentinel-demo/main/demo/loadtest/distributed/setup-worker.sh | bash"
echo "  cd /opt/mqtt-sentinel-demo/demo/loadtest"
echo "  source venv/bin/activate"
echo "  locust -f locustfile.py --worker --master-host=<YOUR_IP>"
echo ""
echo "Then run master locally:"
echo "  ./run-master.sh $NUM_WORKERS 10000 500 300"
