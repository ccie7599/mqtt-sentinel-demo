#!/usr/bin/env python3
"""
Security Injection Scenario Tester

Tests various security scenarios against MQTT Sentinel to verify
threat detection and alerting capabilities.
"""

import os
import ssl
import sys
import time
import base64
import random
import threading
from concurrent.futures import ThreadPoolExecutor

import paho.mqtt.client as mqtt

# Configuration
MQTT_HOST = os.getenv("MQTT_HOST", "172.234.3.122")
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
BRIDGE_USER = os.getenv("BRIDGE_USER", "bridge")
BRIDGE_PASS = os.getenv("BRIDGE_PASS", "bridge-secret-change-me")


def create_client(client_id: str, username: str = None, password: str = None):
    """Create an MQTT client with TLS configured."""
    client = mqtt.Client(
        client_id=client_id,
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    # TLS without cert verification for demo
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    if username:
        client.username_pw_set(username, password or "")

    return client


def test_auth_failure():
    """Scenario 1: Authentication failure with invalid user."""
    print("\n" + "=" * 60)
    print("SCENARIO 1: Authentication Failure")
    print("=" * 60)
    print("Attempting connection with invalid-user-xyz...")

    result = {"connected": False, "error": None}
    connect_event = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            result["connected"] = True
        else:
            result["error"] = f"Connection refused: rc={rc}"
        connect_event.set()

    client = create_client("invalid-user-xyz", "invalid-user-xyz", "wrong-password")
    client.on_connect = on_connect

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        client.loop_start()
        connect_event.wait(timeout=5)
        client.loop_stop()
        client.disconnect()
    except Exception as e:
        result["error"] = str(e)

    if result["connected"]:
        print("✗ UNEXPECTED: Connection succeeded (should have failed)")
    else:
        print(f"✓ EXPECTED: Connection denied - {result['error']}")

    return not result["connected"]


def test_pattern_violation():
    """Scenario 2: Pattern violation with malicious payload."""
    print("\n" + "=" * 60)
    print("SCENARIO 2: Pattern Violation (Command Injection)")
    print("=" * 60)

    payloads = [
        "ALERT; cat /etc/passwd",
        "ALERT && rm -rf /",
        "<script>alert('xss')</script>",
        "'; DROP TABLE users; --",
    ]

    client = create_client("security-tester", BRIDGE_USER, BRIDGE_PASS)
    connected = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            connected.set()

    client.on_connect = on_connect

    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.loop_start()

        if not connected.wait(timeout=10):
            print("✗ Failed to connect as bridge user")
            return False

        print(f"Connected as {BRIDGE_USER}")

        for payload in payloads:
            topic = f"clients/security-test-user/alerts"
            print(f"  Publishing malicious payload: {payload[:40]}...")
            result = client.publish(topic, payload, qos=1)
            result.wait_for_publish()
            time.sleep(0.5)

        print("✓ Malicious payloads published - check security dashboard for alerts")
        client.loop_stop()
        client.disconnect()
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_rate_anomaly():
    """Scenario 3: Rate anomaly with burst connections."""
    print("\n" + "=" * 60)
    print("SCENARIO 3: Rate Anomaly (Burst Connections)")
    print("=" * 60)
    print("Creating 50 rapid connections...")

    success_count = 0
    fail_count = 0

    def attempt_connection(i):
        nonlocal success_count, fail_count
        client_id = f"burst-{i}-{random.randint(1000,9999)}"
        client = create_client(client_id, f"user{i}", "")

        connected = threading.Event()
        result = {"success": False}

        def on_connect(client, userdata, flags, rc, properties=None):
            result["success"] = (rc == 0)
            connected.set()

        client.on_connect = on_connect

        try:
            client.connect(MQTT_HOST, MQTT_PORT)
            client.loop_start()
            connected.wait(timeout=3)
            client.loop_stop()
            client.disconnect()
            return result["success"]
        except:
            return False

    # Rapid burst of connections
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(attempt_connection, range(1, 51)))

    success_count = sum(results)
    fail_count = len(results) - success_count

    print(f"  Connections: {success_count} succeeded, {fail_count} failed")
    print("✓ Burst test complete - check dashboard for rate anomaly alerts")
    return True


def test_size_anomaly():
    """Scenario 4: Size anomaly with large payload."""
    print("\n" + "=" * 60)
    print("SCENARIO 4: Size Anomaly (Large Payload)")
    print("=" * 60)

    # Create a 100KB payload
    large_payload = "X" * (100 * 1024)

    client = create_client("size-tester", BRIDGE_USER, BRIDGE_PASS)
    connected = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            connected.set()

    client.on_connect = on_connect

    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.loop_start()

        if not connected.wait(timeout=10):
            print("✗ Failed to connect")
            return False

        print(f"Publishing 100KB payload...")
        topic = "clients/size-test-user/alerts"
        result = client.publish(topic, large_payload, qos=1)
        result.wait_for_publish()

        print("✓ Large payload published - check dashboard for size anomaly alert")
        client.loop_stop()
        client.disconnect()
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_entropy_anomaly():
    """Scenario 5: High entropy payload (potential encrypted/encoded data)."""
    print("\n" + "=" * 60)
    print("SCENARIO 5: Entropy Anomaly (High Entropy Payload)")
    print("=" * 60)

    # Generate random bytes and base64 encode
    random_bytes = bytes([random.randint(0, 255) for _ in range(1024)])
    high_entropy_payload = base64.b64encode(random_bytes).decode()

    client = create_client("entropy-tester", BRIDGE_USER, BRIDGE_PASS)
    connected = threading.Event()

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            connected.set()

    client.on_connect = on_connect

    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.loop_start()

        if not connected.wait(timeout=10):
            print("✗ Failed to connect")
            return False

        print(f"Publishing high-entropy payload ({len(high_entropy_payload)} bytes)...")
        topic = "clients/entropy-test-user/alerts"
        result = client.publish(topic, high_entropy_payload, qos=1)
        result.wait_for_publish()

        print("✓ High-entropy payload published - check dashboard for entropy alert")
        client.loop_stop()
        client.disconnect()
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("MQTT Sentinel Security Scenario Tester")
    print("=" * 60)
    print(f"Target: {MQTT_HOST}:{MQTT_PORT}")
    print(f"Bridge User: {BRIDGE_USER}")

    results = {
        "Auth Failure": test_auth_failure(),
        "Pattern Violation": test_pattern_violation(),
        "Rate Anomaly": test_rate_anomaly(),
        "Size Anomaly": test_size_anomaly(),
        "Entropy Anomaly": test_entropy_anomaly(),
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for scenario, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {scenario}: {status}")

    print("\n" + "=" * 60)
    print("Check Grafana security dashboard for corresponding alerts")
    print("=" * 60)


if __name__ == "__main__":
    main()
