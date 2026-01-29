#!/usr/bin/env python3
"""
MQTT Sentinel Alert Publisher

Publishes ~600 ALERT messages/sec to Mosquitto upstream broker.
Bridge replicates to NATS cluster for fan-out to subscribers.

Message Flow:
    Publisher (this script)
        │
        ▼ MQTT/TLS
    Mosquitto (upstream)
        │
        ▼ Bridge Service
    NATS JetStream Cluster
        │
        ▼ Fan-out
    1.5M Subscribers

Usage:
    python alert_publisher.py

Configuration (via environment variables):
    MOSQUITTO_HOST  - Mosquitto broker address (default: localhost)
    MOSQUITTO_PORT  - Broker port (default: 8883)
    MOSQUITTO_USER  - Bridge user credentials (default: bridge-user)
    MOSQUITTO_PASS  - Bridge user password (default: bridge-password)
    TARGET_RATE     - Messages per second (default: 600)
    USER_MAX        - Maximum user ID (default: 1500000)
    USE_TLS         - Enable TLS (default: true)
"""

import argparse
import logging
import os
import random
import signal
import ssl
import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Publisher configuration."""
    host: str
    port: int
    username: str
    password: str
    target_rate: int
    user_max: int
    use_tls: bool
    ca_cert_path: Optional[str]
    topic_pattern: str


class AlertPublisher:
    """
    Publishes ALERT messages to random client topics at a target rate.
    """

    def __init__(self, config: Config):
        self.config = config
        self._running = False
        self._connected = False
        self._connect_event = threading.Event()

        # Statistics
        self.messages_sent = 0
        self.messages_failed = 0
        self.start_time: Optional[float] = None
        self._stats_lock = threading.Lock()

        # Create MQTT client
        self.client = mqtt.Client(
            client_id="alert-publisher",
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Handle connection callback."""
        if rc == 0:
            self._connected = True
            self._connect_event.set()
            logger.info("Connected to Mosquitto broker")
        else:
            self._connected = False
            logger.error(f"Connection failed: rc={rc}")

    def _on_disconnect(self, client, userdata, disconnect_flags, rc, properties=None):
        """Handle disconnection callback."""
        self._connected = False
        self._connect_event.clear()
        if rc != 0:
            logger.warning(f"Unexpected disconnect: rc={rc}, will reconnect")

    def _on_publish(self, client, userdata, mid, reason_code=None, properties=None):
        """Handle publish confirmation."""
        with self._stats_lock:
            self.messages_sent += 1

    def connect(self) -> bool:
        """Connect to Mosquitto broker."""
        logger.info(f"Connecting to {self.config.host}:{self.config.port}...")

        try:
            # Set credentials
            self.client.username_pw_set(
                username=self.config.username,
                password=self.config.password
            )

            # Configure TLS if enabled
            if self.config.use_tls:
                if self.config.ca_cert_path:
                    self.client.tls_set(
                        ca_certs=self.config.ca_cert_path,
                        cert_reqs=ssl.CERT_REQUIRED
                    )
                else:
                    # Use TLS without certificate verification (for demo/testing)
                    self.client.tls_set(cert_reqs=ssl.CERT_NONE)
                    self.client.tls_insecure_set(True)
                logger.info("TLS enabled")

            # Connect
            self.client.connect(
                self.config.host,
                self.config.port,
                keepalive=60
            )
            self.client.loop_start()

            # Wait for connection
            if self._connect_event.wait(timeout=10):
                return True
            else:
                logger.error("Connection timeout")
                return False

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from broker."""
        self._running = False
        if self._connected:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Disconnected from broker")

    def publish_alert(self, user_id: int) -> bool:
        """Publish an ALERT message to a specific user's topic."""
        if not self._connected:
            return False

        topic = self.config.topic_pattern.format(client_id=f"user{user_id}")

        try:
            result = self.client.publish(topic, "ALERT", qos=1)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Publish failed: {e}")
            with self._stats_lock:
                self.messages_failed += 1
            return False

    def run(self):
        """Run the publisher main loop."""
        if not self.connect():
            logger.error("Failed to connect, exiting")
            return

        self._running = True
        self.start_time = time.time()

        # Calculate interval for target rate
        interval = 1.0 / self.config.target_rate

        logger.info("=" * 60)
        logger.info("MQTT Sentinel Alert Publisher")
        logger.info("=" * 60)
        logger.info(f"Target rate: {self.config.target_rate} msg/sec")
        logger.info(f"User pool: user1 to user{self.config.user_max}")
        logger.info(f"Topic pattern: {self.config.topic_pattern}")
        logger.info("=" * 60)
        logger.info("Publishing alerts... (Ctrl+C to stop)")

        # Stats reporting thread
        stats_thread = threading.Thread(target=self._report_stats, daemon=True)
        stats_thread.start()

        try:
            while self._running:
                # Select random user
                user_id = random.randint(1, self.config.user_max)

                # Publish alert
                self.publish_alert(user_id)

                # Rate limiting with adaptive sleep
                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            self._running = False
            self._print_final_stats()
            self.disconnect()

    def _report_stats(self):
        """Periodically report statistics."""
        while self._running:
            time.sleep(10)  # Report every 10 seconds

            if not self._running:
                break

            with self._stats_lock:
                elapsed = time.time() - self.start_time if self.start_time else 0
                rate = self.messages_sent / elapsed if elapsed > 0 else 0

                logger.info(
                    f"Stats: {self.messages_sent} sent, "
                    f"{self.messages_failed} failed, "
                    f"{rate:.1f} msg/sec avg"
                )

    def _print_final_stats(self):
        """Print final statistics."""
        with self._stats_lock:
            elapsed = time.time() - self.start_time if self.start_time else 0
            rate = self.messages_sent / elapsed if elapsed > 0 else 0

            logger.info("=" * 60)
            logger.info("Final Statistics")
            logger.info("=" * 60)
            logger.info(f"Total messages sent: {self.messages_sent}")
            logger.info(f"Total messages failed: {self.messages_failed}")
            logger.info(f"Run time: {elapsed:.1f} seconds")
            logger.info(f"Average rate: {rate:.1f} msg/sec")
            logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="MQTT Sentinel Alert Publisher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage with defaults
    python alert_publisher.py

    # Custom broker and rate
    python alert_publisher.py --host mqtt.example.com --rate 1000

    # Using environment variables
    MOSQUITTO_HOST=mqtt.example.com TARGET_RATE=1000 python alert_publisher.py
        """
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MOSQUITTO_HOST", "localhost"),
        help="Mosquitto broker hostname"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MOSQUITTO_PORT", "1883")),
        help="Mosquitto broker port"
    )
    parser.add_argument(
        "--username",
        default=os.getenv("MOSQUITTO_USER", "bridge-user"),
        help="MQTT username"
    )
    parser.add_argument(
        "--password",
        default=os.getenv("MOSQUITTO_PASS", "bridge-password"),
        help="MQTT password"
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=int(os.getenv("TARGET_RATE", "600")),
        help="Target messages per second"
    )
    parser.add_argument(
        "--user-max",
        type=int,
        default=int(os.getenv("USER_MAX", "1500000")),
        help="Maximum user ID in pool"
    )
    parser.add_argument(
        "--no-tls",
        action="store_true",
        help="Disable TLS"
    )
    parser.add_argument(
        "--ca-cert",
        default=os.getenv("CA_CERT_PATH"),
        help="Path to CA certificate"
    )
    parser.add_argument(
        "--topic-pattern",
        default=os.getenv("TOPIC_PATTERN", "clients/{client_id}/alerts"),
        help="Topic pattern ({client_id} is replaced)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine TLS setting
    use_tls = os.getenv("USE_TLS", "false").lower() == "true"
    if args.no_tls:
        use_tls = False

    config = Config(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        target_rate=args.rate,
        user_max=args.user_max,
        use_tls=use_tls,
        ca_cert_path=args.ca_cert,
        topic_pattern=args.topic_pattern
    )

    # Set up signal handlers
    publisher = AlertPublisher(config)

    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        publisher._running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run publisher
    publisher.run()


if __name__ == "__main__":
    main()
