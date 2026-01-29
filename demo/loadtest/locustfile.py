"""
MQTT Sentinel Load Testing - Fan-Out Subscriber Simulation

This module simulates 1.5M subscribers connecting to MQTT Sentinel,
each subscribing to their own alert topic for fan-out message delivery.

Usage:
    locust -f locustfile.py --host=mqtts://sentinel.example.com:8883

    With web UI:
    locust -f locustfile.py --host=mqtts://sentinel.example.com:8883 --web-host=0.0.0.0

Configuration (via environment variables):
    NATS_URL        - NATS server URL (default: nats://localhost:4222)
    USE_TLS         - Enable TLS (default: true)
    CA_CERT_PATH    - Path to CA certificate
    USER_MAX        - Maximum user ID (default: 1500000)
"""

import logging
import os
import random
import ssl
import threading
import time
from typing import Optional

import yaml
from locust import User, task, between, events
import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load configuration
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.yaml')

def load_config():
    """Load configuration from YAML file or environment variables."""
    config = {
        'nats_url': os.getenv('NATS_URL', 'nats://localhost:4222'),
        'mqtt_broker': os.getenv('MQTT_BROKER', 'localhost'),
        'mqtt_port': int(os.getenv('MQTT_PORT', '1883')),
        'use_tls': os.getenv('USE_TLS', 'false').lower() == 'true',
        'ca_cert_path': os.getenv('CA_CERT_PATH'),
        'user_max': int(os.getenv('USER_MAX', '1500000')),
        'topic_pattern': os.getenv('TOPIC_PATTERN', 'clients/{client_id}/alerts'),
    }

    # Try to load from YAML file
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config.update(yaml_config)
        except Exception as e:
            logger.warning(f"Failed to load config.yaml: {e}")

    return config

CONFIG = load_config()


class MQTTSubscriberClient:
    """MQTT client that subscribes to a single alert topic."""

    def __init__(self, client_id: str, environment):
        self.client_id = client_id
        self.environment = environment
        self._connected = False
        self._connect_start: Optional[float] = None
        self.messages_received = 0
        self.last_message_time: Optional[float] = None
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
        self.client.on_message = self._on_message
        self.client.on_subscribe = self._on_subscribe

    def connect(self) -> bool:
        """Connect to MQTT broker and subscribe to alert topic."""
        self._connect_start = time.time()

        try:
            # Configure TLS if enabled
            if CONFIG['use_tls']:
                if CONFIG['ca_cert_path']:
                    self.client.tls_set(
                        ca_certs=CONFIG['ca_cert_path'],
                        cert_reqs=ssl.CERT_REQUIRED
                    )
                else:
                    # Use TLS without certificate verification (for demo/testing)
                    self.client.tls_set(cert_reqs=ssl.CERT_NONE)
                    self.client.tls_insecure_set(True)

            # Set credentials (client_id only auth for demo)
            self.client.username_pw_set(username=self.client_id, password="")

            # Connect
            self.client.connect(
                CONFIG['mqtt_broker'],
                CONFIG['mqtt_port'],
                keepalive=60
            )
            self.client.loop_start()

            # Wait for connection with timeout
            timeout = 10
            start = time.time()
            while not self._connected and (time.time() - start) < timeout:
                time.sleep(0.1)

            return self._connected

        except Exception as e:
            response_time = (time.time() - self._connect_start) * 1000 if self._connect_start else 0
            self.environment.events.request.fire(
                request_type="MQTT",
                name="connect",
                response_time=response_time,
                response_length=0,
                exception=e,
                context={}
            )
            logger.error(f"Connection failed for {self.client_id}: {e}")
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
                context={}
            )

            # Subscribe to this client's alert topic
            topic = CONFIG['topic_pattern'].format(client_id=self.client_id)
            self.client.subscribe(topic, qos=1)
            logger.debug(f"{self.client_id} connected and subscribing to {topic}")
        else:
            self._connected = False
            self.environment.events.request.fire(
                request_type="MQTT",
                name="connect",
                response_time=response_time,
                response_length=0,
                exception=Exception(f"Connect failed: rc={rc}"),
                context={}
            )
            logger.warning(f"{self.client_id} connection failed: rc={rc}")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        """Handle disconnection callback."""
        self._connected = False
        if rc != 0:
            logger.warning(f"{self.client_id} unexpected disconnect: rc={rc}")

    def _on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        """Handle subscription confirmation."""
        topic = CONFIG['topic_pattern'].format(client_id=self.client_id)
        self.environment.events.request.fire(
            request_type="MQTT",
            name="subscribe",
            response_time=0,
            response_length=0,
            exception=None,
            context={"topic": topic}
        )
        logger.debug(f"{self.client_id} subscribed successfully")

    def _on_message(self, client, userdata, msg):
        """Handle incoming alert message."""
        with self._lock:
            self.messages_received += 1
            self.last_message_time = time.time()

        # Validate payload is expected "ALERT" message
        payload = msg.payload.decode('utf-8', errors='replace')
        is_valid = payload == "ALERT"

        self.environment.events.request.fire(
            request_type="MQTT",
            name="alert_received",
            response_time=0,
            response_length=len(msg.payload),
            exception=None if is_valid else Exception(f"Unexpected payload: {payload[:50]}"),
            context={"topic": msg.topic, "valid": is_valid}
        )

        if is_valid:
            logger.debug(f"{self.client_id} received ALERT on {msg.topic}")
        else:
            logger.warning(f"{self.client_id} received unexpected payload: {payload[:50]}")

    def disconnect(self):
        """Disconnect from broker."""
        if self._connected:
            self.client.loop_stop()
            self.client.disconnect()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


class AlertSubscriber(User):
    """
    Locust user simulating an MQTT subscriber waiting for alerts.

    Behavior:
    - Connects as a random user from user1..user1500000
    - Subscribes to clients/{client_id}/alerts
    - Waits for alert messages (passive - alerts pushed by publisher)
    """

    # Keep connection alive, minimal task activity
    wait_time = between(1, 2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Select a random user from the pool
        user_num = random.randint(1, CONFIG['user_max'])
        self.client_id = f"user{user_num}"
        self.mqtt_client: Optional[MQTTSubscriberClient] = None

    def on_start(self):
        """Called when user starts - connect and subscribe."""
        self.mqtt_client = MQTTSubscriberClient(self.client_id, self.environment)
        if not self.mqtt_client.connect():
            logger.error(f"Failed to connect {self.client_id}")

    def on_stop(self):
        """Called when user stops - disconnect."""
        if self.mqtt_client:
            self.mqtt_client.disconnect()

    @task
    def wait_for_alert(self):
        """
        Maintain connection and wait for alerts.

        This is a passive task - alerts are pushed by the publisher.
        We just need to keep the connection alive and let the
        on_message callback handle incoming alerts.
        """
        if not self.mqtt_client or not self.mqtt_client.is_connected:
            # Try to reconnect
            logger.info(f"Reconnecting {self.client_id}...")
            if self.mqtt_client:
                self.mqtt_client.disconnect()
            self.mqtt_client = MQTTSubscriberClient(self.client_id, self.environment)
            self.mqtt_client.connect()
            return

        # Just wait - alerts are delivered asynchronously
        time.sleep(1)


class BurstSubscriber(User):
    """
    Subscriber that connects/disconnects frequently to test connection handling.
    Lower weight means fewer of these users.
    """

    wait_time = between(5, 15)
    weight = 1  # Low weight - few burst subscribers

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user_num = random.randint(1, CONFIG['user_max'])
        self.client_id = f"burst-user{user_num}"
        self.mqtt_client: Optional[MQTTSubscriberClient] = None

    @task
    def connect_disconnect_cycle(self):
        """Rapidly connect, subscribe, wait briefly, then disconnect."""
        self.mqtt_client = MQTTSubscriberClient(self.client_id, self.environment)

        if self.mqtt_client.connect():
            # Stay connected briefly
            time.sleep(random.uniform(2, 5))

        self.mqtt_client.disconnect()


# Event hooks for custom reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    logger.info("=" * 60)
    logger.info("MQTT Sentinel Load Test Starting")
    logger.info("=" * 60)
    logger.info(f"MQTT Broker: {CONFIG['mqtt_broker']}:{CONFIG['mqtt_port']}")
    logger.info(f"User pool: user1 to user{CONFIG['user_max']}")
    logger.info(f"Topic pattern: {CONFIG['topic_pattern']}")
    logger.info(f"TLS enabled: {CONFIG['use_tls']}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    logger.info("=" * 60)
    logger.info("MQTT Sentinel Load Test Complete")
    logger.info("=" * 60)


# Custom stats tracking
alert_stats = {
    'total_received': 0,
    'valid_alerts': 0,
    'invalid_alerts': 0,
}
stats_lock = threading.Lock()


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """Track alert-specific metrics."""
    if request_type == "MQTT" and name == "alert_received":
        with stats_lock:
            alert_stats['total_received'] += 1
            if context.get('valid', False):
                alert_stats['valid_alerts'] += 1
            else:
                alert_stats['invalid_alerts'] += 1


@events.report_to_master.add_listener
def on_report_to_master(client_id, data):
    """Send custom stats to master in distributed mode."""
    with stats_lock:
        data['alert_stats'] = alert_stats.copy()


@events.worker_report.add_listener
def on_worker_report(client_id, data):
    """Aggregate custom stats from workers in distributed mode."""
    if 'alert_stats' in data:
        with stats_lock:
            for key in alert_stats:
                alert_stats[key] += data['alert_stats'].get(key, 0)
