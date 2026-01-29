# MQTT Sentinel Architecture

## Overview

MQTT Sentinel provides a secure, scalable MQTT infrastructure capable of handling millions of concurrent device connections while providing real-time security inspection and threat detection.

## System Components

### Sentinel Core (Distributed Real-Time Message Broker)

The heart of MQTT Sentinel is a distributed message broker cluster that provides:

- **Horizontal Scalability**: Add nodes to handle increased load
- **High Availability**: Automatic failover with no message loss
- **Durable Persistence**: Message storage with configurable retention
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

Device authentication is handled through in-band Auth Callout:

- Client connects to MQTT Sentinel
- Sentinel makes Auth Callout request to customer's Auth DB
- Auth DB validates client credentials and returns permissions
- Sentinel accepts or rejects connection based on response
- Audit logging of all authentication events

### Observability Stack

Complete visibility into system behavior:

- **Prometheus**: Metrics collection and storage
- **Grafana**: Real-time dashboards and alerting
- **Structured Logging**: JSON-formatted logs for analysis

## Message Flow

### Full System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CUSTOMER ORIGIN                                     │
│                                                                                  │
│  ┌─────────────┐         ┌─────────────┐                                        │
│  │   Auth DB   │         │  Mosquitto  │◀─── Alert Publisher (~600 msg/sec)     │
│  │  (Clients)  │         │   Broker    │                                        │
│  └──────▲──────┘         └──────┬──────┘                                        │
│         │                       │                                                │
└─────────┼───────────────────────┼───────────────────────────────────────────────┘
          │                       │
          │ Auth Callout          │ WebSocket Bridge
          │ (in-band)             ▼
          │              ┌────────────────┐
          │              │      WAF       │
          │              └───────┬────────┘
          │                      │
          │                      ▼
┌─────────┼──────────────────────────────────────────────────────────────────────┐
│         │                  MQTT SENTINEL                                        │
│         │     Secure MQTT at Scale — Millions of Connections                    │
├─────────┼──────────────────────────────────────────────────────────────────────┤
│         │                                                                       │
│  ┌──────┴────────────────────────────────────────────────────────────────────┐ │
│  │              Distributed Real-Time Message Broker                          │ │
│  │                    (72-hour message retention)                             │ │
│  └─────────────────────────────────┬─────────────────────────────────────────┘ │
│                                    │                                            │
│     ┌──────────────────────────────┼──────────────────────────────┐            │
│     │                              │                              │            │
│     ▼                              ▼                              ▼            │
│ ┌────────┐                    ┌────────┐                    ┌──────────┐       │
│ │ user1  │                    │ user2  │        ...         │ user N   │       │
│ │(client)│                    │(client)│                    │ (client) │       │
│ └────────┘                    └────────┘                    └──────────┘       │
│                                                                                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Fan-Out Alert Distribution

The demo showcases efficient alert distribution to millions of subscribers:

1. **Publisher** sends alerts to upstream Mosquitto broker (Customer Origin)
2. **WebSocket Bridge** connects Mosquitto to MQTT Sentinel through WAF
3. **Distributed Broker** persists messages with 72-hour retention
4. **Subscribers** receive alerts on their individual topics

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
│ • Broker Node │    │ • Broker Node │    │ • Broker Node │
│ • Inspector   │    │ • Inspector   │    │ • Inspector   │
│ • Auth Cache  │    │ • Auth Cache  │    │ • Auth Cache  │
└───────────────┘    └───────────────┘    └───────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │     CUSTOMER ORIGIN      │
              │  ┌────────┐  ┌────────┐  │
              │  │Auth DB │  │Mosquitto│ │
              │  └────────┘  └────────┘  │
              └──────────────────────────┘
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

## Broker Configuration

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
- In-band Auth Callout to customer Auth DB
- Audit logging for compliance
- Rate limiting at multiple layers
- Pattern-based threat detection
