# MQTT Sentinel Architecture

## Overview

MQTT Sentinel provides a secure, scalable MQTT infrastructure capable of handling millions of concurrent device connections while providing real-time security inspection and threat detection.

## System Components

### Sentinel Core (NATS Cluster)

The heart of MQTT Sentinel is a distributed NATS cluster that provides:

- **Horizontal Scalability**: Add nodes to handle increased load
- **High Availability**: Automatic failover with no message loss
- **JetStream Persistence**: Durable message storage with configurable retention
- **Geographic Distribution**: Multi-region deployment support

### Threat Defense Layer

All messages pass through the security inspection pipeline:

```
┌──────────────────────────────────────────────────────────────┐
│                   Security Inspection Pipeline                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────┐    ┌────────────┐    ┌────────────────┐     │
│  │  Pattern   │───▶│  Anomaly   │───▶│  Auth          │     │
│  │  Matching  │    │  Detection │    │  Verification  │     │
│  └────────────┘    └────────────┘    └────────────────┘     │
│        │                 │                   │               │
│        ▼                 ▼                   ▼               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Security Event Aggregator               │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│                          ▼                                   │
│                   ┌─────────────┐                           │
│                   │  Dashboard  │                           │
│                   │  & Alerts   │                           │
│                   └─────────────┘                           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Authentication Service

Device authentication is handled through:

- Client ID validation against registered device database
- Automatic credential verification
- Regional distribution for low-latency auth decisions
- Audit logging of all authentication events

### Observability Stack

Complete visibility into system behavior:

- **Prometheus**: Metrics collection and storage
- **Grafana**: Real-time dashboards and alerting
- **Structured Logging**: JSON-formatted logs for analysis

## Message Flow

### Fan-Out Alert Distribution

The demo showcases efficient alert distribution to millions of subscribers:

1. **Publisher** sends alerts to upstream Mosquitto broker
2. **Bridge Service** replicates messages to NATS cluster
3. **NATS JetStream** persists messages with 72-hour retention
4. **Subscribers** receive alerts on their individual topics

```
Publisher (600 msg/sec)
        │
        ▼
┌───────────────┐
│   Mosquitto   │
│   (Upstream)  │
└───────┬───────┘
        │
        ▼
┌───────────────────────────────────────┐
│         NATS JetStream Cluster        │
│                                       │
│  Stream: MQTT_ALERTS                  │
│  Retention: 72 hours                  │
│  Replicas: 3                          │
│                                       │
│  Subjects: clients.*.alerts           │
└───────────────────────────────────────┘
        │
        ├─────────────────┬─────────────────┐
        ▼                 ▼                 ▼
    ┌───────┐         ┌───────┐         ┌───────┐
    │ user1 │         │ user2 │         │ userN │
    └───────┘         └───────┘         └───────┘
```

### Topic Structure

Each client subscribes to their own alert topic:

```
clients/{client_id}/alerts
```

This ensures:
- **Privacy**: Clients only receive their own alerts
- **Efficiency**: No unnecessary message filtering on clients
- **Scalability**: Topic-based routing scales horizontally

## Deployment Architecture

### Multi-Region Setup

```
                    ┌─────────────────┐
                    │  Global Load    │
                    │    Balancer     │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   US-EAST     │    │   EU-WEST     │    │   AP-SOUTH    │
│   Region      │    │   Region      │    │   Region      │
│               │    │               │    │               │
│ • NATS Node   │    │ • NATS Node   │    │ • NATS Node   │
│ • Inspector   │    │ • Inspector   │    │ • Inspector   │
│ • Auth Cache  │    │ • Auth Cache  │    │ • Auth Cache  │
└───────────────┘    └───────────────┘    └───────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────┴────────┐
                    │  Central Auth   │
                    │    Database     │
                    └─────────────────┘
```

### Regional Distribution

Default client distribution across regions:
- **US-EAST**: 50% (750,000 clients)
- **EU-WEST**: 30% (450,000 clients)
- **AP-SOUTH**: 20% (300,000 clients)

## Performance Characteristics

| Metric | Target |
|--------|--------|
| Concurrent Connections | 1,500,000+ |
| Message Throughput | 600+ msg/sec |
| Auth Latency (P99) | < 10ms |
| Message Delivery (P99) | < 50ms |
| Availability | 99.99% |

## JetStream Configuration

Message persistence configuration for 72-hour retention:

```yaml
streams:
  - name: MQTT_ALERTS
    subjects:
      - "clients.*.alerts"
    retention: limits
    max_age: 72h
    storage: file
    replicas: 3
    discard: old
```

## Security Considerations

- All external connections use TLS 1.3
- Inter-node communication encrypted
- Audit logging for compliance
- Rate limiting at multiple layers
- Pattern-based threat detection
