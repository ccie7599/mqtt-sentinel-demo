#!/bin/bash
#
# MQTT Sentinel Demo - Main Orchestration Script
# Starts all demo components in the correct order
#
# Usage: ./run-demo.sh [COMMAND]
#
# Commands:
#   start      Start the full demo environment
#   stop       Stop all demo components
#   status     Show status of demo components
#   logs       Show logs from demo components
#   clean      Clean up all demo data

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$SCRIPT_DIR")"
ROOT_DIR="$(dirname "$DEMO_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
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

log_step() {
    echo -e "${CYAN}${BOLD}==>${NC} $1"
}

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║   ███╗   ███╗ ██████╗ ████████╗████████╗                    ║"
    echo "║   ████╗ ████║██╔═══██╗╚══██╔══╝╚══██╔══╝                    ║"
    echo "║   ██╔████╔██║██║   ██║   ██║      ██║                       ║"
    echo "║   ██║╚██╔╝██║██║▄▄ ██║   ██║      ██║                       ║"
    echo "║   ██║ ╚═╝ ██║╚██████╔╝   ██║      ██║                       ║"
    echo "║   ╚═╝     ╚═╝ ╚══▀▀═╝    ╚═╝      ╚═╝                       ║"
    echo "║                                                              ║"
    echo "║   ███████╗███████╗███╗   ██╗████████╗██╗███╗   ██╗███████╗  ║"
    echo "║   ██╔════╝██╔════╝████╗  ██║╚══██╔══╝██║████╗  ██║██╔════╝  ║"
    echo "║   ███████╗█████╗  ██╔██╗ ██║   ██║   ██║██╔██╗ ██║█████╗    ║"
    echo "║   ╚════██║██╔══╝  ██║╚██╗██║   ██║   ██║██║╚██╗██║██╔══╝    ║"
    echo "║   ███████║███████╗██║ ╚████║   ██║   ██║██║ ╚████║███████╗  ║"
    echo "║   ╚══════╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚══════╝  ║"
    echo "║                                                              ║"
    echo "║            Secure MQTT at Scale - 2M+ Connections            ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

check_dependencies() {
    log_step "Checking dependencies..."

    local missing=()

    command -v docker &> /dev/null || missing+=("docker")
    command -v docker-compose &> /dev/null || missing+=("docker-compose")
    command -v python3 &> /dev/null || missing+=("python3")
    command -v pip3 &> /dev/null || missing+=("pip3")

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Missing dependencies: ${missing[*]}"
        log_error "Please install the missing tools and try again."
        exit 1
    fi

    log_info "All dependencies found"
}

start_infrastructure() {
    log_step "Starting infrastructure (Grafana, Prometheus)..."

    cd "$ROOT_DIR"
    docker-compose up -d

    log_info "Waiting for services to be healthy..."
    sleep 10

    # Check if services are running
    if docker-compose ps | grep -q "Up"; then
        log_info "Infrastructure started successfully"
    else
        log_error "Failed to start infrastructure"
        docker-compose logs
        exit 1
    fi
}

populate_database() {
    log_step "Populating authentication database..."

    if [ -f "$SCRIPT_DIR/populate-db.sh" ]; then
        bash "$SCRIPT_DIR/populate-db.sh"
    else
        log_warn "Database population script not found, skipping..."
    fi
}

install_python_deps() {
    log_step "Installing Python dependencies..."

    # Install loadtest dependencies
    if [ -f "$DEMO_DIR/loadtest/requirements.txt" ]; then
        pip3 install -q -r "$DEMO_DIR/loadtest/requirements.txt"
    fi

    # Install publisher dependencies
    if [ -f "$DEMO_DIR/publisher/requirements.txt" ]; then
        pip3 install -q -r "$DEMO_DIR/publisher/requirements.txt"
    fi

    log_info "Python dependencies installed"
}

start_publisher() {
    log_step "Starting alert publisher..."

    cd "$DEMO_DIR/publisher"

    # Start publisher in background
    nohup python3 alert_publisher.py > /tmp/mqtt-sentinel-publisher.log 2>&1 &
    PUBLISHER_PID=$!
    echo $PUBLISHER_PID > /tmp/mqtt-sentinel-publisher.pid

    log_info "Publisher started (PID: $PUBLISHER_PID)"
    log_info "Logs: /tmp/mqtt-sentinel-publisher.log"
}

show_status() {
    log_step "Demo Component Status"
    echo ""

    # Check Docker containers
    echo "Docker Containers:"
    if command -v docker-compose &> /dev/null; then
        cd "$ROOT_DIR" 2>/dev/null && docker-compose ps 2>/dev/null || echo "  No containers running"
    fi
    echo ""

    # Check publisher
    echo "Alert Publisher:"
    if [ -f /tmp/mqtt-sentinel-publisher.pid ]; then
        PID=$(cat /tmp/mqtt-sentinel-publisher.pid)
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "  Status: ${GREEN}Running${NC} (PID: $PID)"
        else
            echo -e "  Status: ${RED}Stopped${NC}"
        fi
    else
        echo -e "  Status: ${YELLOW}Not started${NC}"
    fi
    echo ""

    # Check Locust
    echo "Locust Load Test:"
    if pgrep -f "locust" > /dev/null 2>&1; then
        echo -e "  Status: ${GREEN}Running${NC}"
    else
        echo -e "  Status: ${YELLOW}Not started${NC}"
    fi
    echo ""

    # Show URLs
    echo "Dashboard URLs:"
    echo "  Grafana:     http://localhost:3000"
    echo "  Prometheus:  http://localhost:9090"
    echo "  Locust UI:   http://localhost:8089 (when running)"
}

stop_demo() {
    log_step "Stopping demo components..."

    # Stop publisher
    if [ -f /tmp/mqtt-sentinel-publisher.pid ]; then
        PID=$(cat /tmp/mqtt-sentinel-publisher.pid)
        if ps -p $PID > /dev/null 2>&1; then
            kill $PID 2>/dev/null || true
            log_info "Publisher stopped"
        fi
        rm -f /tmp/mqtt-sentinel-publisher.pid
    fi

    # Stop Locust
    pkill -f "locust" 2>/dev/null || true

    # Stop Docker containers
    cd "$ROOT_DIR"
    docker-compose down 2>/dev/null || true

    log_info "All demo components stopped"
}

show_logs() {
    log_step "Demo Logs"

    echo ""
    echo "=== Publisher Logs ==="
    if [ -f /tmp/mqtt-sentinel-publisher.log ]; then
        tail -50 /tmp/mqtt-sentinel-publisher.log
    else
        echo "No publisher logs found"
    fi

    echo ""
    echo "=== Docker Logs ==="
    cd "$ROOT_DIR"
    docker-compose logs --tail=50 2>/dev/null || echo "No Docker logs found"
}

clean_demo() {
    log_step "Cleaning up demo data..."

    # Stop everything first
    stop_demo

    # Remove log files
    rm -f /tmp/mqtt-sentinel-*.log
    rm -f /tmp/mqtt-sentinel-*.pid

    # Remove Docker volumes
    cd "$ROOT_DIR"
    docker-compose down -v 2>/dev/null || true

    log_info "Cleanup complete"
}

start_demo() {
    print_banner

    log_info "Starting MQTT Sentinel Demo"
    log_info "==========================="
    echo ""

    check_dependencies
    echo ""

    start_infrastructure
    echo ""

    install_python_deps
    echo ""

    # Optionally populate database
    read -p "Populate database with 1.5M users? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        populate_database
        echo ""
    fi

    # Optionally start publisher
    read -p "Start alert publisher? (y/N) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        start_publisher
        echo ""
    fi

    log_info "Demo environment is ready!"
    echo ""
    show_status
    echo ""

    log_info "Next steps:"
    echo "  1. Open Grafana: http://localhost:3000"
    echo "  2. Start load test: cd demo/loadtest && locust -f locustfile.py"
    echo "  3. Inject security events: ./demo/scripts/inject-security.sh"
}

usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start      Start the full demo environment (default)"
    echo "  stop       Stop all demo components"
    echo "  status     Show status of demo components"
    echo "  logs       Show logs from demo components"
    echo "  clean      Clean up all demo data"
    echo "  --help     Show this help message"
    exit 0
}

# Main
case "${1:-start}" in
    start)
        start_demo
        ;;
    stop)
        stop_demo
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    clean)
        clean_demo
        ;;
    --help|-h)
        usage
        ;;
    *)
        log_error "Unknown command: $1"
        usage
        ;;
esac
