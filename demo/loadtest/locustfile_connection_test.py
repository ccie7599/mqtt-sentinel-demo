#!/usr/bin/env python3
"""
MQTT Sentinel Connection Load Test

Tests connection success rate and latency for MQTT clients authenticating
via auth-callout. Each Locust user gets a unique client_id to avoid
duplicate connection rejections.

Usage:
    # Start with web UI
    locust -f locustfile_connection_test.py --host=mqtts://198.74.59.108:443

    # Headless mode (2000 users, 100/sec spawn rate, 60s duration)
    locust -f locustfile_connection_test.py --host=mqtts://198.74.59.108:443 \
        --headless -u 2000 -r 100 -t 60s

Environment variables:
    MQTT_BROKER     - Broker hostname/IP (default: from --host)
    MQTT_PORT       - Broker port (default: 443)
    USE_TLS         - Enable TLS (default: true)
    USER_PREFIX     - Client ID prefix (default: user)
    USER_START      - Starting user number (default: 1)
    USER_MAX        - Maximum user number in database (default: 1500000)
"""

import logging
import os
import random
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Optional

from locust import User, task, between, events
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global user ID counter for unique assignments
_user_counter = 0
_user_counter_lock = threading.Lock()


def get_next_user_id() -> int:
    """Get the next unique user ID (thread-safe)."""
    global _user_counter
    with _user_counter_lock:
        _user_counter += 1
        return _user_counter


@dataclass
class Config:
    """Load test configuration."""
    mqtt_broker: str = ""
    mqtt_port: int = 443
    use_tls: bool = True
    user_prefix: str = "user"
    user_start: int = 1
    user_max: int = 1500000
    connect_timeout: int = 30
    keepalive: int = 60


def load_config() -> Config:
    """Load configuration from environment variables."""
    config = Config()
    config.mqtt_broker = os.getenv('MQTT_BROKER', '')
    config.mqtt_port = int(os.getenv('MQTT_PORT', '443'))
    config.use_tls = os.getenv('USE_TLS', 'true').lower() == 'true'
    config.user_prefix = os.getenv('USER_PREFIX', 'user')
    config.user_start = int(os.getenv('USER_START', '1'))
    config.user_max = int(os.getenv('USER_MAX', '1500000'))
    config.connect_timeout = int(os.getenv('CONNECT_TIMEOUT', '30'))
    return config


CONFIG = load_config()


class MQTTConnectionClient:
    """MQTT client wrapper that tracks connection metrics."""

    def __init__(self, client_id: str, environment):
        self.client_id = client_id
        self.environment = environment
        self._connected = False
        self._connect_start: Optional[float] = None
        self._connect_error: Optional[str] = None
        self._lock = threading.Lock()

        # Create MQTT client
        self.client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def connect(self, broker: str, port: int, use_tls: bool = True) -> bool:
        """Connect to MQTT broker. Returns True if successful."""
        self._connect_start = time.time()
        self._connect_error = None

        try:
            # Configure TLS
            if use_tls:
                self.client.tls_set(cert_reqs=ssl.CERT_NONE)
                self.client.tls_insecure_set(True)

            # Set username (client_id for auth-callout)
            self.client.username_pw_set(username=self.client_id, password="")

            # Connect
            self.client.connect(broker, port, keepalive=CONFIG.keepalive)
            self.client.loop_start()

            # Wait for connection with timeout
            timeout = CONFIG.connect_timeout
            start = time.time()
            while not self._connected and not self._connect_error and (time.time() - start) < timeout:
                time.sleep(0.05)

            if self._connected:
                return True
            elif self._connect_error:
                raise Exception(self._connect_error)
            else:
                raise Exception(f"Connection timeout ({timeout}s)")

        except Exception as e:
            response_time = (time.time() - self._connect_start) * 1000
            self.environment.events.request.fire(
                request_type="MQTT",
                name="connect",
                response_time=response_time,
                response_length=0,
                exception=e,
                context={"client_id": self.client_id}
            )
            logger.debug(f"Connection failed for {self.client_id}: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Handle connection callback."""
        response_time = (time.time() - self._connect_start) * 1000 if self._connect_start else 0

        if rc == 0:
            self._connected = True
            self.environment.events.request.fire(
                request_type="MQTT",
                name="connect",
                response_time=response_time,
                response_length=0,
                exception=None,
                context={"client_id": self.client_id}
            )
            logger.debug(f"{self.client_id} connected in {response_time:.1f}ms")
        else:
            rc_messages = {
                1: "Incorrect protocol version",
                2: "Invalid client identifier",
                3: "Server unavailable",
                4: "Bad username or password",
                5: "Not authorized",
            }
            error_msg = rc_messages.get(rc, f"Unknown error (rc={rc})")
            self._connect_error = error_msg

            self.environment.events.request.fire(
                request_type="MQTT",
                name="connect",
                response_time=response_time,
                response_length=0,
                exception=Exception(error_msg),
                context={"client_id": self.client_id, "rc": rc}
            )
            logger.debug(f"{self.client_id} connection failed: {error_msg}")

    def _on_disconnect(self, client, userdata, disconnect_flags, rc, properties=None):
        """Handle disconnection callback."""
        self._connected = False
        if rc != 0:
            logger.debug(f"{self.client_id} unexpected disconnect: rc={rc}")

    def disconnect(self):
        """Disconnect from broker."""
        if self._connected:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


class MQTTConnectionUser(User):
    """
    Locust user that connects to MQTT broker and maintains connection.

    Each user gets a unique client_id based on spawn order to avoid
    duplicate connection rejections from NATS.
    """

    wait_time = between(1, 3)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get unique user ID
        user_num = CONFIG.user_start + get_next_user_id() - 1
        self.client_id = f"{CONFIG.user_prefix}{user_num}"
        self.mqtt_client: Optional[MQTTConnectionClient] = None

        # Parse broker from host
        self.broker = CONFIG.mqtt_broker
        self.port = CONFIG.mqtt_port

        if not self.broker and self.host:
            # Parse from --host argument (e.g., mqtts://192.168.1.1:8883)
            host = self.host
            if host.startswith("mqtts://"):
                host = host[8:]
                self.use_tls = True
            elif host.startswith("mqtt://"):
                host = host[7:]
                self.use_tls = False
            else:
                self.use_tls = CONFIG.use_tls

            if ":" in host:
                self.broker, port_str = host.split(":", 1)
                self.port = int(port_str)
            else:
                self.broker = host
        else:
            self.use_tls = CONFIG.use_tls

    def on_start(self):
        """Called when user starts - connect to broker."""
        logger.info(f"Starting user {self.client_id} -> {self.broker}:{self.port}")
        self.mqtt_client = MQTTConnectionClient(self.client_id, self.environment)
        self.mqtt_client.connect(self.broker, self.port, self.use_tls)

    def on_stop(self):
        """Called when user stops - disconnect."""
        if self.mqtt_client:
            self.mqtt_client.disconnect()

    @task
    def maintain_connection(self):
        """Keep connection alive and reconnect if needed."""
        if not self.mqtt_client or not self.mqtt_client.is_connected:
            # Record reconnection attempt
            if self.mqtt_client:
                self.mqtt_client.disconnect()

            self.mqtt_client = MQTTConnectionClient(self.client_id, self.environment)
            self.mqtt_client.connect(self.broker, self.port, self.use_tls)


# Connection statistics
connection_stats = {
    'total_attempts': 0,
    'successful': 0,
    'failed': 0,
    'auth_failures': 0,
}
stats_lock = threading.Lock()


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """Track connection statistics."""
    if request_type == "MQTT" and name == "connect":
        with stats_lock:
            connection_stats['total_attempts'] += 1
            if exception:
                connection_stats['failed'] += 1
                if context and context.get('rc') in (4, 5):
                    connection_stats['auth_failures'] += 1
            else:
                connection_stats['successful'] += 1


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    # Reset user counter
    global _user_counter
    with _user_counter_lock:
        _user_counter = 0

    logger.info("=" * 60)
    logger.info("MQTT Connection Load Test Starting")
    logger.info("=" * 60)
    logger.info(f"User pool: {CONFIG.user_prefix}{CONFIG.user_start} to {CONFIG.user_prefix}{CONFIG.user_max}")
    logger.info(f"TLS enabled: {CONFIG.use_tls}")
    logger.info(f"Connect timeout: {CONFIG.connect_timeout}s")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    logger.info("=" * 60)
    logger.info("MQTT Connection Load Test Complete")
    logger.info("=" * 60)
    with stats_lock:
        logger.info(f"Total connection attempts: {connection_stats['total_attempts']}")
        logger.info(f"Successful: {connection_stats['successful']}")
        logger.info(f"Failed: {connection_stats['failed']}")
        logger.info(f"Auth failures: {connection_stats['auth_failures']}")
        if connection_stats['total_attempts'] > 0:
            success_rate = connection_stats['successful'] / connection_stats['total_attempts'] * 100
            logger.info(f"Success rate: {success_rate:.1f}%")
    logger.info("=" * 60)
