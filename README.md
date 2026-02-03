# MQTT Sentinel

**Distributed MQTT Security Platform — Protecting IoT at Scale**

MQTT Sentinel is a multi-layered security platform that protects MQTT deployments with distributed edge proxies, deep packet inspection, and seamless integration with existing WAF infrastructure. Designed for millions of concurrent device connections with real-time threat detection and total observability.

## Architecture

![MQTT Sentinel Architecture](images/mqtt-sentinel-architecture.png)

MQTT Sentinel operates as a transparent security layer between IoT devices and your origin infrastructure:

| Layer | Function |
|-------|----------|
| **Proxy Layer** | Distributed, multi-region edge proxies handling TLS termination, rate limiting, authentication, and MQTT protocol validation |
| **Core Broker** | Centralized message broker with payload inspection, anomaly detection, and 72-hour message buffering |
| **Bridge Service** | Protocol conversion from MQTT to WebSockets, enabling traffic to pass through existing WAF infrastructure |
| **Customer WAF** | Your existing Akamai or F5 WAF inspects WebSocket traffic before it reaches origin |
| **Customer Origin** | Envoy proxy fronting Mosquitto broker, with PerconaDB for device authentication |

## Key Benefits

| Benefit | Description |
|---------|-------------|
| **Distributed Security** | Proxy layer deployed multi-region, close to devices. Absorb attacks at the edge before they reach your origin. |
| **L3/L4 DDoS Protection** | Edge proxies absorb volumetric and protocol-level attacks with multi-tier rate limiting (global, per-IP, per-client, per-packet-type). |
| **Application Layer Protection** | MQTT 3.1.1 protocol validation at the proxy, plus deep payload inspection at the broker (SQL injection, XSS, command injection, path traversal detection). |
| **Origin Protection** | MQTT protocol converted to WebSockets by the Bridge Service, making all traffic inspectable by your existing WAF (Akamai / F5). No direct MQTT exposure to origin. |
| **Total Observability** | Prometheus metrics and Grafana dashboards across all layers — proxy connections, rate limit events, auth results, inspection findings, and bridge throughput. |
| **Performance & Scale** | 1,000,000+ concurrent connections, 72-hour message retention with 3x replication. |

## Detailed Diagrams

| Diagram | Description |
|---------|-------------|
| [Architecture Overview](images/mqtt-sentinel-architecture.png) | End-to-end flow from devices through Sentinel to customer origin |
| [Proxy Layer Detail](images/proxy-layer-detail.png) | TLS termination, rate limiting pipeline, auth callout, MQTT validation |
| [Security Inspection](images/security-inspection.png) | Pattern matching, anomaly detection, message buffering pipeline |
| [Bridge & Origin](images/bridge-and-origin.png) | MQTT-to-WebSocket conversion, WAF integration, customer origin |

## Demo

### Prerequisites

- `mosquitto-clients` package installed (`brew install mosquitto` on macOS)
- Network access to the MQTT Sentinel cluster
- Grafana dashboard access

### Live Demo Walkthrough

Run the interactive demo script that walks through each capability:

```bash
./demo/scripts/demo-walkthrough.sh
```

This demonstrates:
1. Platform health and connection metrics
2. Device authentication (valid + invalid credentials)
3. Rate limiting under burst traffic
4. Security inspection catching malicious payloads
5. Grafana dashboard visualization
6. Scale metrics

### Traffic Simulation

Generate continuous bad traffic to visualize security events in Grafana:

```bash
# Run all attack types in a loop
./demo/scripts/simulate-bad-traffic.sh

# Run specific attack type
./demo/scripts/simulate-bad-traffic.sh --mode auth-flood
./demo/scripts/simulate-bad-traffic.sh --mode injection
./demo/scripts/simulate-bad-traffic.sh --mode connection-flood
./demo/scripts/simulate-bad-traffic.sh --mode size-anomaly
```

### Security Scenario Injection

Run discrete security test scenarios:

```bash
./demo/scripts/inject-security.sh [SCENARIO]
# Scenarios: all, auth-failure, rate-anomaly, pattern-violation, size-anomaly, entropy
```

### Load Testing

Subscriber fan-out load test using Locust:

```bash
cd demo/loadtest
pip install -r requirements.txt
locust -f locustfile.py --host=mqtts://mqtt.connected-cloud.io:30883
```

## Documentation

- [Architecture Details](docs/architecture.md) — Detailed system design with proxy, broker, bridge, and origin layers
- [Security Features](docs/security-features.md) — Threat detection capabilities across all layers

## Dashboard — MQTT Security Dashboard

The Grafana dashboard provides real-time visibility across the entire platform. Panels are organized into the following sections:

### Overview

| Panel | Type | Description |
|-------|------|-------------|
| Connection Rate | Stat | Rate of new MQTT connections per second |
| Active Proxy Connections | Stat | Currently active connections through the proxy layer |
| Active MQTT Sessions | Stat | Total active sessions on the core broker |
| Auth Success Rate | Gauge | Percentage of successful authentication requests |
| Rate Limit Rejection % | Gauge | Percentage of requests rejected by rate limiting |

### Rate Limiting

| Panel | Type | Description |
|-------|------|-------------|
| Rate Limits by Type | Time series | Rate limit events by tier (global, per-IP, per-client, CONNECT, PUBLISH, SUBSCRIBE) |
| Rejections by Type | Time series | Rejected requests by rate limit tier |

### Authentication

| Panel | Type | Description |
|-------|------|-------------|
| Auth Requests by Result | Time series | Auth outcomes: allowed, denied, cache hit, error |
| Auth Latency (P50/P95/P99) | Time series | Authentication callout latency percentiles |

### Proxy Latency

| Panel | Type | Description |
|-------|------|-------------|
| Preread Phase Latency | Time series | Combined latency for packet parsing, rate limiting, and auth (P50/P95/P99) |
| Upstream Broker Connect Latency | Time series | Time to establish connection to the core broker (P50/P95/P99) |
| Packet Forward Latency by Direction | Time series | MQTT packet forwarding latency, client→broker and broker→client (P95/P99) |
| End-to-End Connection Setup Latency | Time series | Total time for complete connection establishment (P50/P95/P99) |

### Connections

| Panel | Type | Description |
|-------|------|-------------|
| Connections Opened/Rejected | Time series | Rate of connection opens vs rejections |
| Rejection Reasons | Pie chart | Distribution of rejection reasons (auth failed, rate limited, etc.) |

### MQTT Packets

| Panel | Type | Description |
|-------|------|-------------|
| Packets/sec by Type | Time series | Packet throughput by MQTT packet type (CONNECT, PUBLISH, SUBSCRIBE, etc.) |
| Bytes/sec by Type | Time series | Data throughput by MQTT packet type |
| Inbound vs Outbound | Time series | Packet rates split by direction |

### Broker

| Panel | Type | Description |
|-------|------|-------------|
| Message Throughput | Time series | Broker message throughput (total, successful, failed) |
| Broker JVM Heap | Time series | Broker memory usage and limits |

### Infrastructure Health

| Panel | Type | Description |
|-------|------|-------------|
| Service Health | Stat | UP/DOWN status for all platform components |
| Cache Clients | Time series | Connected and blocked clients on the session cache |
| Message Bus Throughput | Time series | Produce and consume throughput on the message bus |

## Performance

| Metric | Target |
|--------|--------|
| Concurrent Connections | 1,000,000+ |
| Message Throughput | 600+ msg/sec |
| Auth Latency (P99) | < 10ms |
| Message Delivery (P99) | Regional: < 50ms, Cross-region: < 200ms |
| Availability | 99.99% |
| Message Retention | 72 hours |

## License

Apache License 2.0 — See [LICENSE](LICENSE) for details.
