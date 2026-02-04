# MQTT Sentinel Security Features

## Overview

MQTT Sentinel provides defense-in-depth across three layers: the distributed proxy layer, the core broker inspection engine, and the bridge-to-WAF origin protection. Each layer adds distinct security capabilities that work together to protect IoT deployments.

## Defense-in-Depth Security Model

```
Platform: Infrastructure        Layer 1: Proxy (Edge)        Layer 2: Core Broker         Layer 3: Bridge + WAF
────────────────────────        ─────────────────────        ────────────────────         ──────────────────────
• Region-level DDoS             • TLS termination            • Pattern matching           • Protocol conversion
• Prolexic on-demand            • Multi-tier rate limiting   • Anomaly detection          • WAF-friendly traffic
  network scrubbing             • Auth callout               • Payload quarantine         • Origin isolation
                                • MQTT validation            • Security event logging     • Geo-blocking
                                • L3/L4 DDoS absorption      • Message buffering          • Bot detection
```

## Platform-Level Network Security

Before traffic reaches any MQTT Sentinel component, it passes through infrastructure-level network protections provided by the underlying Linode compute platform.

### Region-Level DDoS Protection

Every Linode region includes built-in DDoS mitigation at the network edge. This always-on protection operates at the infrastructure level and defends against:

- Volumetric attacks (UDP floods, ICMP floods, amplification attacks)
- Protocol-level attacks (SYN floods, fragmented packets)
- Network-layer anomalies detected and dropped before reaching compute instances

This protection is automatic — no configuration required, no additional cost, and no performance impact during normal operation.

### Akamai Prolexic Routed On-Demand

For sustained or large-scale network-layer attacks that exceed region-level DDoS capacity, Akamai Prolexic routed on-demand is implemented:

- **Activation**: On-demand — traffic is rerouted to Prolexic scrubbing centers when an attack is detected
- **Scrubbing**: Network-layer traffic is inspected and malicious packets are dropped at Prolexic's globally distributed scrubbing centers
- **Clean traffic return**: Legitimate traffic is forwarded back to the Linode region via GRE tunnels
- **Capacity**: Prolexic's scrubbing infrastructure absorbs multi-terabit attacks
- **Coverage**: Protects all platform IP space used by MQTT Sentinel proxy and broker instances

### How Platform Security Fits the Architecture

```
Internet Traffic
       │
       ▼
┌──────────────────────────────┐
│  Linode Region-Level DDoS    │  ← Always-on, automatic
│  + Prolexic On-Demand        │  ← Activated during attacks
└──────────────┬───────────────┘
               │ Clean network traffic
               ▼
┌──────────────────────────────┐
│  Layer 1: Proxy Fleet        │  ← Application-level DDoS, rate limiting
└──────────────┬───────────────┘
               │
               ▼
       Layers 2 & 3 ...
```

Platform-level protections handle network-layer (L3/L4) volumetric attacks at the infrastructure edge. The MQTT Sentinel proxy layer then handles application-layer (L7) attacks specific to the MQTT protocol. Together, these provide defense-in-depth from the network edge through to the application layer.

## Layer 1: Proxy Layer Security

### Rate Limiting

The proxy enforces rate limits at six tiers before traffic reaches the core broker:

| Tier | Key | Default | Purpose |
|------|-----|---------|---------|
| Global | All traffic | 10K req/s | Platform-wide flood protection |
| Per-IP | Source IP | 100 req/s | Single-source attack mitigation |
| CONNECT | Source IP | 10 req/s | Authentication brute-force prevention |
| PUBLISH | Client ID | 100 req/s | Message flood prevention |
| SUBSCRIBE | Client ID | 20 req/s | Subscription abuse prevention |
| Per-Client | Client ID | 50 req/s | Per-device rate cap |

Rate limit rejections are handled per MQTT packet type:
- **CONNECT**: CONNACK with return code 0x05 (Not Authorized)
- **PUBLISH QoS 0**: Dropped silently
- **PUBLISH QoS 1+**: No PUBACK (client retries with backoff)
- **SUBSCRIBE**: SUBACK with failure code 0x80

### Authentication

Device authentication uses an external callout to the customer's PerconaDB:

```
Client                    Proxy                  Customer PerconaDB
  │                         │                           │
  │── CONNECT ─────────────>│                           │
  │  (client_id, user, pw)  │                           │
  │                         │── Check auth cache ──>    │
  │                         │   (miss)                  │
  │                         │── HTTP POST /mqtt/auth ──>│
  │                         │   {client_id, user, pw}   │
  │                         │<── 200 OK / 401 Denied ───│
  │                         │── Cache result (60s) ──>  │
  │<── CONNACK (allow/deny)─│                           │
```

- Fail-closed: unreachable auth service = connection denied
- Cache TTL: 60 seconds (configurable)
- Auth results logged for audit

### MQTT Protocol Validation

The proxy parses every MQTT packet and enforces:
- Protocol name "MQTT" with level 4 (MQTT 3.1.1)
- First packet must be CONNECT
- Valid remaining length encoding (1-4 bytes)
- Valid packet types (1-14)
- Required fields present per packet type

Malformed packets are rejected at the edge before reaching the broker.

### L3/L4 DDoS Protection

The distributed proxy fleet provides:
- Geographic distribution absorbs volumetric attacks regionally
- TCP connection limits per source IP
- Horizontal scaling by adding proxy nodes
- Rate limiting at multiple tiers prevents amplification

## Layer 2: Core Broker Security

### Pattern Matching (Signature-Based Detection)

The inspection engine scans all message payloads against threat signatures:

| Threat Type | Pattern Examples | Severity | Action |
|-------------|-----------------|----------|--------|
| SQL Injection | `' OR '1'='1`, `UNION SELECT`, `DROP TABLE` | High | Block |
| Command Injection | `; cat /etc/passwd`, `&& rm -rf`, `$(curl ...)` | Critical | Block |
| XSS | `<script>`, `javascript:`, `onerror=` | High | Block |
| Path Traversal | `../../../etc/passwd`, `..\\windows\\` | High | Block |

Pattern rules are configurable in YAML format:

```yaml
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

### Anomaly Detection (Behavioral Analysis)

The broker tracks behavioral baselines and detects deviations:

#### Rate Anomaly
- **Baseline**: Normal connection rate per client
- **Threshold**: 100+ connections/second
- **Action**: Rate limit applied, security event logged
- **Dashboard**: Rate anomaly counter, source breakdown

#### Size Anomaly
- **Baseline**: Expected payload size per message type
- **Threshold**: Payloads exceeding 10KB
- **Action**: Message quarantined, event logged
- **Dashboard**: Size anomaly counter, payload size histogram

#### Entropy Anomaly
- **Purpose**: Detect encrypted, compressed, or encoded malicious payloads
- **Method**: Shannon entropy calculation on payload bytes
- **Threshold**: Entropy > 7.5 (high entropy indicates binary/encrypted data)
- **Action**: Flagged for review, event logged
- **Dashboard**: Entropy anomaly counter

## Layer 3: Origin Protection

### Protocol Conversion

The Bridge Service converts MQTT traffic to WebSockets before it reaches the customer origin. This is the key architectural decision that enables origin protection:

**Problem**: Raw MQTT is a binary protocol that standard WAFs cannot inspect.

**Solution**: Convert to WebSockets (WSS), which WAFs like Akamai and F5 can analyze at the application layer.

### WAF Integration

With traffic converted to WebSockets, the customer's existing WAF provides:
- Application-layer payload inspection
- Bot detection and mitigation
- Geographic access controls
- Additional rate limiting
- DDoS mitigation at the WAF edge

### Origin Isolation

The customer's origin (Envoy + Mosquitto) is never exposed to raw MQTT traffic from the internet:
- All device connections terminate at the proxy layer
- Bridge Service initiates outbound WebSocket connections to origin
- Origin only accepts connections from the Bridge Service
- No inbound internet traffic reaches origin directly

## Security Scenarios

### Scenario 1: Authentication Brute Force

**Attack**: Rapid CONNECT attempts with invalid credentials.

**Defense chain**:
1. Proxy CONNECT rate limit (10 req/s per IP) throttles attempts
2. Per-IP rate limit (100 req/s) caps total traffic
3. Auth callout denies invalid credentials
4. Security event logged with source IP
5. Grafana dashboard shows auth failure spike

### Scenario 2: Message Injection Attack

**Attack**: Authenticated client sends payload containing SQL injection.

**Defense chain**:
1. Proxy validates MQTT protocol structure (passes — valid MQTT)
2. Core broker pattern matcher detects SQL injection signature
3. Message blocked, not delivered to subscribers
4. Security event logged with payload hash and client ID
5. Grafana dashboard shows pattern violation alert

### Scenario 3: Volumetric DDoS

**Attack**: Flood of TCP connections from distributed sources.

**Defense chain**:
1. Linode region-level DDoS drops obvious volumetric/protocol-level floods at the infrastructure edge
2. Prolexic on-demand activates for sustained large-scale attacks, scrubbing network traffic before it reaches compute
3. Regional proxy fleet absorbs remaining traffic geographically
4. Global rate limit (10K req/s) caps platform-wide throughput
5. Per-IP limits (100 req/s) throttle individual sources
6. Core broker never sees the attack traffic
7. Origin is completely isolated

### Scenario 4: Encoded Payload Exfiltration

**Attack**: Data exfiltration using base64-encoded payloads in MQTT messages.

**Defense chain**:
1. Proxy passes the valid MQTT packet
2. Core broker entropy detector flags Shannon entropy > 7.5
3. Message flagged for review
4. Security event logged
5. Grafana dashboard shows entropy anomaly

### Scenario 5: Oversized Payload

**Attack**: Abnormally large payload to exploit buffer vulnerabilities.

**Defense chain**:
1. Proxy validates MQTT packet structure
2. Core broker size anomaly detector flags payload > 10KB
3. Message quarantined
4. Security event logged with payload size
5. Grafana dashboard shows size anomaly

## Security Dashboard Metrics

### Real-Time Indicators

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| Threat Score | Composite security health score | > 50 |
| Auth Failure Rate | Failed authentications per minute | > 10/min |
| Rate Limit Rejections | Requests rejected by rate limiting | > 100/min |
| Blocked Messages | Messages blocked by inspection | > 5/min |
| Pattern Violations | Injection attempts detected | Any |
| Anomaly Events | Rate/size/entropy anomalies | > 3/min |

### Security Event Log

The dashboard displays the 50 most recent security events:

| Field | Description |
|-------|-------------|
| Timestamp | Event occurrence time |
| Layer | proxy, broker, or bridge |
| Event Type | auth_failure, rate_limit, pattern_violation, anomaly |
| Severity | low, medium, high, critical |
| Source | Client ID or IP address |
| Details | Event-specific information |
