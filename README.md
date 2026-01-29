# MQTT Sentinel

**Secure MQTT at Scale — 2M+ Concurrent Connections**

MQTT Sentinel is an enterprise-grade security layer for MQTT deployments, providing real-time threat detection, authentication, and message inspection at massive scale.

## Key Capabilities

| Feature | Description |
|---------|-------------|
| **Massive Scale** | 1.5M+ concurrent device connections with sub-millisecond latency |
| **Fan-Out Distribution** | Efficient alert delivery to millions of subscribers |
| **Real-Time Security** | Pattern matching, anomaly detection, and threat prevention |
| **Authentication** | Secure device authentication with automatic credential validation |
| **Observability** | Comprehensive Grafana dashboards for health and security monitoring |
| **Message Retention** | 72-hour message history with JetStream persistence |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       MQTT SENTINEL                              │
│            Secure MQTT at Scale — 2M+ Connections                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐     ┌─────────────────┐     ┌──────────────┐     │
│   │  1.5M    │────▶│  Sentinel Core  │────▶│   Sentinel   │     │
│   │ Devices  │     │  (NATS Cluster) │     │  Dashboard   │     │
│   └──────────┘     └────────┬────────┘     └──────────────┘     │
│                             │                                    │
│                             ▼                                    │
│                    ┌─────────────────┐                          │
│                    │ Threat Defense  │                          │
│                    │ • Pattern Match │                          │
│                    │ • Anomaly Det.  │                          │
│                    │ • Auth Verify   │                          │
│                    └─────────────────┘                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Demo Scenario

This demo showcases MQTT Sentinel handling a realistic enterprise workload:

| Parameter | Value |
|-----------|-------|
| Concurrent Clients | 1,500,000 |
| Message Pattern | Fan-out (alerts to per-client topics) |
| Message Rate | ~600 msg/sec aggregate |
| Payload | Plain text alerts |
| QoS | 1 (at least once delivery) |
| Retention | 72 hours |
| Topic Pattern | `clients/{client_id}/alerts` |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.9+
- Access to MQTT Sentinel cluster

### Running the Demo

1. **Populate the authentication database:**
   ```bash
   ./demo/scripts/populate-db.sh
   ```

2. **Start the demo environment:**
   ```bash
   ./demo/scripts/run-demo.sh
   ```

3. **Launch subscriber load test:**
   ```bash
   cd demo/loadtest
   pip install -r requirements.txt
   locust -f locustfile.py --host=mqtts://sentinel.example.com:8883
   ```

4. **Start the alert publisher:**
   ```bash
   cd demo/publisher
   pip install -r requirements.txt
   python alert_publisher.py
   ```

5. **Open Grafana dashboards:**
   - System Health: http://localhost:3000/d/sentinel-health
   - Security Alerts: http://localhost:3000/d/sentinel-security

### Security Injection Testing

Trigger security scenarios to see threat detection in action:

```bash
./demo/scripts/inject-security.sh
```

This will simulate:
- Authentication failures
- Rate anomalies (burst attacks)
- Pattern violations (injection attempts)
- Payload size anomalies
- High entropy detection

## Documentation

- [Architecture Overview](docs/architecture.md) — High-level system design
- [Security Features](docs/security-features.md) — Threat detection capabilities

## Dashboards

### Sentinel Health Dashboard
Monitor system health including:
- Connected device count
- Alert throughput (target: 600 msg/sec)
- Cluster health status
- Message retention metrics
- System latency (P50, P95, P99)

### Sentinel Security Dashboard
Track security events including:
- Threat score indicator
- Authentication failures
- Blocked messages
- Pattern violations
- Anomaly events
- Security event log

## Message Flow

```
┌─────────────┐     MQTT/TLS      ┌─────────────┐
│   Alert     │ ────────────────▶ │  Mosquitto  │
│  Publisher  │  ~600 msg/sec     │  (Upstream) │
└─────────────┘                   └──────┬──────┘
                                         │
                                         │ Bridge Service
                                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    MQTT SENTINEL                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              NATS JetStream Cluster                  │    │
│  │  Stream: MQTT_ALERTS (72hr retention)               │    │
│  │  Subjects: clients.*.alerts                         │    │
│  └─────────────────────────┬───────────────────────────┘    │
│                            │                                 │
│      ┌─────────────────────┼─────────────────────┐          │
│      ▼                     ▼                     ▼          │
│  ┌───────┐            ┌───────┐           ┌───────────┐    │
│  │ user1 │            │ user2 │           │ user1.5M  │    │
│  └───────┘            └───────┘           └───────────┘    │
│                                                             │
│  Each device receives ONLY alerts for their own topic       │
└─────────────────────────────────────────────────────────────┘
```

## License

Apache License 2.0 — See [LICENSE](LICENSE) for details.

## Support

For enterprise support and licensing inquiries, contact your MQTT Sentinel representative.
