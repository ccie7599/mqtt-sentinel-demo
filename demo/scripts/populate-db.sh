#!/bin/bash
#
# MQTT Sentinel Demo - Database Population Script
# Generates 1.5M users in the authentication database
#
# Usage: ./populate-db.sh [OPTIONS]
#
# Options:
#   --host      Database host (default: localhost)
#   --port      Database port (default: 5432)
#   --db        Database name (default: mqtt_sentinel)
#   --user      Database user (default: sentinel)
#   --batch     Batch size (default: 10000)
#   --total     Total users to create (default: 1500000)
#   --dry-run   Print SQL without executing

set -euo pipefail

# Default configuration
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-mqtt_sentinel}"
DB_USER="${DB_USER:-sentinel}"
DB_PASSWORD="${DB_PASSWORD:-}"
BATCH_SIZE="${BATCH_SIZE:-10000}"
TOTAL_USERS="${TOTAL_USERS:-1500000}"
DRY_RUN=false

# Region distribution (percentages)
US_EAST_PCT=50
EU_WEST_PCT=30
AP_SOUTH_PCT=20

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --host HOST      Database host (default: localhost)"
    echo "  --port PORT      Database port (default: 5432)"
    echo "  --db NAME        Database name (default: mqtt_sentinel)"
    echo "  --user USER      Database user (default: sentinel)"
    echo "  --batch SIZE     Batch size (default: 10000)"
    echo "  --total COUNT    Total users (default: 1500000)"
    echo "  --dry-run        Print SQL without executing"
    echo "  --help           Show this help message"
    echo ""
    echo "Environment variables:"
    echo "  DB_PASSWORD      Database password"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            DB_HOST="$2"
            shift 2
            ;;
        --port)
            DB_PORT="$2"
            shift 2
            ;;
        --db)
            DB_NAME="$2"
            shift 2
            ;;
        --user)
            DB_USER="$2"
            shift 2
            ;;
        --batch)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --total)
            TOTAL_USERS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Calculate regional distribution
US_EAST_COUNT=$((TOTAL_USERS * US_EAST_PCT / 100))
EU_WEST_COUNT=$((TOTAL_USERS * EU_WEST_PCT / 100))
AP_SOUTH_COUNT=$((TOTAL_USERS - US_EAST_COUNT - EU_WEST_COUNT))

log_info "MQTT Sentinel Database Population"
log_info "=================================="
log_info "Database: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
log_info "Total users: ${TOTAL_USERS}"
log_info "Batch size: ${BATCH_SIZE}"
log_info ""
log_info "Regional distribution:"
log_info "  US-EAST: ${US_EAST_COUNT} (${US_EAST_PCT}%)"
log_info "  EU-WEST: ${EU_WEST_COUNT} (${EU_WEST_PCT}%)"
log_info "  AP-SOUTH: ${AP_SOUTH_COUNT} (${AP_SOUTH_PCT}%)"
log_info ""

# Create table if not exists
CREATE_TABLE_SQL=$(cat <<'EOF'
CREATE TABLE IF NOT EXISTS mqtt_clients (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) UNIQUE NOT NULL,
    secret_hash VARCHAR(255) DEFAULT '',
    region VARCHAR(50) NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mqtt_clients_client_id ON mqtt_clients(client_id);
CREATE INDEX IF NOT EXISTS idx_mqtt_clients_region ON mqtt_clients(region);
CREATE INDEX IF NOT EXISTS idx_mqtt_clients_enabled ON mqtt_clients(enabled);
EOF
)

# Function to determine region based on user number
get_region() {
    local user_num=$1
    if [ $user_num -le $US_EAST_COUNT ]; then
        echo "us-east"
    elif [ $user_num -le $((US_EAST_COUNT + EU_WEST_COUNT)) ]; then
        echo "eu-west"
    else
        echo "ap-south"
    fi
}

# Function to generate batch SQL
generate_batch_sql() {
    local start=$1
    local end=$2

    echo "INSERT INTO mqtt_clients (client_id, secret_hash, region, enabled) VALUES"

    local first=true
    for i in $(seq $start $end); do
        local region=$(get_region $i)
        if [ "$first" = true ]; then
            first=false
        else
            echo ","
        fi
        echo -n "  ('user${i}', '', '${region}', true)"
    done
    echo ";"
}

# Function to execute SQL
execute_sql() {
    local sql="$1"

    if [ "$DRY_RUN" = true ]; then
        echo "$sql"
        return 0
    fi

    if [ -n "$DB_PASSWORD" ]; then
        PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "$sql" > /dev/null
    else
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "$sql" > /dev/null
    fi
}

# Create table
log_info "Creating table if not exists..."
if [ "$DRY_RUN" = true ]; then
    echo "$CREATE_TABLE_SQL"
else
    execute_sql "$CREATE_TABLE_SQL"
fi

# Clear existing data (optional)
log_warn "Clearing existing data..."
execute_sql "TRUNCATE TABLE mqtt_clients RESTART IDENTITY;"

# Generate and insert users in batches
log_info "Inserting ${TOTAL_USERS} users in batches of ${BATCH_SIZE}..."

total_batches=$(( (TOTAL_USERS + BATCH_SIZE - 1) / BATCH_SIZE ))
current_batch=0
start_time=$(date +%s)

for batch_start in $(seq 1 $BATCH_SIZE $TOTAL_USERS); do
    batch_end=$((batch_start + BATCH_SIZE - 1))
    if [ $batch_end -gt $TOTAL_USERS ]; then
        batch_end=$TOTAL_USERS
    fi

    current_batch=$((current_batch + 1))

    # Generate and execute batch SQL
    batch_sql=$(generate_batch_sql $batch_start $batch_end)

    if [ "$DRY_RUN" = true ]; then
        echo "-- Batch ${current_batch}/${total_batches}: users ${batch_start}-${batch_end}"
        echo "$batch_sql"
        echo ""
    else
        execute_sql "$batch_sql"

        # Progress indicator
        progress=$((current_batch * 100 / total_batches))
        elapsed=$(($(date +%s) - start_time))
        if [ $current_batch -gt 0 ] && [ $elapsed -gt 0 ]; then
            rate=$((current_batch * BATCH_SIZE / elapsed))
            eta=$(( (total_batches - current_batch) * BATCH_SIZE / rate ))
            printf "\r[%3d%%] Batch %d/%d | %d users/sec | ETA: %ds     " \
                $progress $current_batch $total_batches $rate $eta
        fi
    fi
done

if [ "$DRY_RUN" = false ]; then
    echo ""
    log_info "Population complete!"

    # Verify counts
    log_info "Verifying regional distribution..."

    us_count=$(execute_sql "SELECT COUNT(*) FROM mqtt_clients WHERE region = 'us-east';" 2>/dev/null || echo "0")
    eu_count=$(execute_sql "SELECT COUNT(*) FROM mqtt_clients WHERE region = 'eu-west';" 2>/dev/null || echo "0")
    ap_count=$(execute_sql "SELECT COUNT(*) FROM mqtt_clients WHERE region = 'ap-south';" 2>/dev/null || echo "0")

    log_info "Final counts:"
    log_info "  US-EAST: ${us_count}"
    log_info "  EU-WEST: ${eu_count}"
    log_info "  AP-SOUTH: ${ap_count}"
fi

log_info "Done!"
