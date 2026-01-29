# MQTT Sentinel Security Features

## Overview

MQTT Sentinel provides comprehensive security capabilities designed to protect IoT deployments at scale. All messages pass through a multi-layer security inspection pipeline before delivery.

## Security Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    Security Inspection Pipeline                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Incoming    ┌──────────┐   ┌──────────┐   ┌──────────┐        │
│  Message ───▶│ Pattern  │──▶│ Anomaly  │──▶│  Auth    │──▶ OK  │
│              │ Matching │   │Detection │   │ Verify   │        │
│              └────┬─────┘   └────┬─────┘   └────┬─────┘        │
│                   │              │              │               │
│                   ▼              ▼              ▼               │
│              ┌─────────────────────────────────────────┐       │
│              │         Security Event Log              │       │
│              │         (Grafana Dashboard)             │       │
│              └─────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Pattern Matching

### Valid Payload Detection

For the alert system, valid payloads must match expected patterns:

| Rule | Pattern | Action |
|------|---------|--------|
| Valid Alert | `^ALERT$` | Allow |
| Any Other | `.*` | Flag for review |

### Threat Pattern Detection

The following patterns trigger security alerts:

| Threat Type | Pattern Example | Severity |
|-------------|-----------------|----------|
| SQL Injection | `' OR '1'='1` | High |
| Command Injection | `; cat /etc/passwd` | Critical |
| XSS Attempt | `<script>` | High |
| Path Traversal | `../../../` | High |

### Configuration

Pattern rules are defined in YAML format:

```yaml
alert_validation:
  - name: valid_alert_payload
    pattern: "^ALERT$"
    action: allow

  - name: suspicious_payload
    pattern: ".*"
    action: flag
    severity: medium

threat_patterns:
  - name: sql_injection
    pattern: "('|\")?\\s*(OR|AND)\\s+.*=.*"
    action: block
    severity: high

  - name: command_injection
    pattern: "[;&|`$]\\s*(cat|ls|rm|wget|curl)"
    action: block
    severity: critical

  - name: xss_attempt
    pattern: "<script[^>]*>"
    action: block
    severity: high
```

## Anomaly Detection

### Heuristic Analysis

MQTT Sentinel employs multiple heuristics to detect anomalous behavior:

#### Rate Anomaly Detection
- **Baseline**: Normal connection rate per client
- **Threshold**: 100+ connections/second triggers alert
- **Action**: Rate limiting applied, event logged

#### Size Anomaly Detection
- **Baseline**: Expected payload size for message type
- **Threshold**: Payloads exceeding 10KB flagged
- **Action**: Message quarantined, event logged

#### Entropy Detection
- **Purpose**: Detect encrypted/encoded malicious payloads
- **Method**: Shannon entropy calculation
- **Threshold**: Entropy > 7.5 indicates potential binary/encrypted data
- **Action**: Flag for review, event logged

### Behavioral Analysis

```
┌────────────────────────────────────────────────────────────┐
│                  Behavioral Baselines                       │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Client Behavior Profile                                   │
│  ├── Normal connection frequency                           │
│  ├── Typical message rate                                  │
│  ├── Expected payload sizes                                │
│  └── Geographic access patterns                            │
│                                                            │
│  Deviation Detection                                       │
│  ├── Sudden rate increase → Rate Anomaly                  │
│  ├── Unusual payload size → Size Anomaly                  │
│  ├── New geographic origin → Location Anomaly             │
│  └── Off-hours activity → Temporal Anomaly                │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Authentication

### Client Authentication Flow

```
┌────────┐      ┌─────────────┐      ┌──────────┐
│ Client │─────▶│  Sentinel   │─────▶│  Auth    │
│        │ TLS  │   Gateway   │      │  Service │
└────────┘      └──────┬──────┘      └────┬─────┘
                       │                   │
                       │ Verify Client ID  │
                       │◀──────────────────│
                       │                   │
                       │   ┌───────────┐   │
                       │   │ Auth DB   │   │
                       │   │ 1.5M      │   │
                       │   │ clients   │   │
                       │   └───────────┘   │
                       │                   │
                ┌──────┴──────┐            │
                │  Allow/Deny │            │
                └─────────────┘            │
```

### Authentication Events

| Event | Description | Dashboard Display |
|-------|-------------|-------------------|
| Auth Success | Valid client authenticated | Green indicator |
| Auth Failure | Invalid client ID rejected | Red counter |
| Auth Timeout | Auth service unreachable | Yellow warning |

## Security Scenarios

### Scenario 1: Authentication Failure

**Trigger**: Connection attempt with invalid client ID
```bash
mosquitto_pub -u "invalid-user-xyz" -t "test" -m "test"
```

**Expected Response**:
- Connection rejected
- Auth failure logged
- Dashboard counter incremented

### Scenario 2: Rate Anomaly (Burst Attack)

**Trigger**: Rapid connection attempts
```bash
for i in {1..100}; do
  mosquitto_pub -u "attacker$i" -t "test" -m "ALERT" &
done
```

**Expected Response**:
- Rate limit triggered
- Anomaly alert generated
- Source IP flagged

### Scenario 3: Pattern Violation (Injection Attempt)

**Trigger**: Malicious payload
```bash
mosquitto_pub -u "user1" -t "inject" -m "ALERT; cat /etc/passwd"
```

**Expected Response**:
- Message blocked
- Security alert: Command injection detected
- Event logged with full payload

### Scenario 4: Size Anomaly

**Trigger**: Oversized payload
```bash
mosquitto_pub -u "user1" -t "test" -m "$(head -c 100000 /dev/urandom | base64)"
```

**Expected Response**:
- Message quarantined
- Size anomaly alert
- Payload hash logged

### Scenario 5: High Entropy Detection

**Trigger**: Encoded/encrypted payload
```bash
mosquitto_pub -u "user1" -t "test" -m "$(echo 'malicious binary' | base64)"
```

**Expected Response**:
- Entropy analysis triggered
- High entropy alert generated
- Message flagged for review

## Security Dashboard Metrics

### Real-Time Indicators

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| Threat Score | Composite security health | > 50 |
| Auth Failure Rate | Failed authentications/min | > 10/min |
| Blocked Messages | Messages blocked/min | > 5/min |
| Pattern Violations | Injection attempts detected | Any |
| Anomaly Events | Rate/size/entropy anomalies | > 3/min |

### Security Event Log

The dashboard displays the 50 most recent security events:

| Field | Description |
|-------|-------------|
| Timestamp | Event occurrence time |
| Event Type | auth_failure, pattern_violation, anomaly |
| Severity | low, medium, high, critical |
| Source | Client ID or IP address |
| Details | Event-specific information |

## Best Practices

### For Operators

1. **Monitor dashboards** during high-traffic periods
2. **Review security logs** daily for emerging patterns
3. **Update pattern rules** based on new threat intelligence
4. **Tune anomaly thresholds** for your specific workload

### For Developers

1. **Use expected payload formats** (plain `ALERT` text)
2. **Handle auth failures gracefully** with exponential backoff
3. **Implement client-side validation** before publishing
4. **Log security events** for debugging
