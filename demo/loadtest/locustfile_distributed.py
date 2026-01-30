#!/usr/bin/env python3
"""
MQTT Sentinel Distributed Connection Load Test (gmqtt version)

Uses gmqtt (asyncio-based) for much better performance than paho-mqtt.
Designed for distributed load testing across multiple worker nodes.

User ID Assignment:
- User IDs are partitioned across workers based on worker_index
- Within each worker, users are assigned sequentially
- This ensures no duplicate client_ids across the entire test

Environment variables:
    MQTT_BROKER     - Broker hostname/IP (default: from --host)
    MQTT_PORT       - Broker port (default: 443)
    USE_TLS         - Enable TLS (default: true)
    USER_PREFIX     - Client ID prefix (default: user)
    USER_POOL_SIZE  - Total users in database (default: 1500000)
    WORKER_INDEX    - This worker's index (0-based)
    WORKER_COUNT    - Total number of workers
"""

import asyncio
import logging
import os
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import Future

from locust import User, task, between, events
from gmqtt import Client as MQTTClient
from gmqtt.mqtt.constants import MQTTv311

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Load test configuration."""
    mqtt_broker: str = ""
    mqtt_port: int = 443
    use_tls: bool = True
    user_prefix: str = "user"
    user_pool_size: int = 1500000
    worker_index: int = 0
    worker_count: int = 1
    users_per_worker: int = 10000
    connect_timeout: int = 30
    keepalive: int = 60


def load_config() -> Config:
    """Load configuration from environment variables."""
    config = Config()
    config.mqtt_broker = os.getenv('MQTT_BROKER', '')
    config.mqtt_port = int(os.getenv('MQTT_PORT', '443'))
    config.use_tls = os.getenv('USE_TLS', 'true').lower() == 'true'
    config.user_prefix = os.getenv('USER_PREFIX', 'user')
    config.user_pool_size = int(os.getenv('USER_POOL_SIZE', '1500000'))
    config.worker_index = int(os.getenv('WORKER_INDEX', '0'))
    config.worker_count = int(os.getenv('WORKER_COUNT', '1'))
    config.users_per_worker = int(os.getenv('USERS_PER_WORKER', '10000'))
    config.connect_timeout = int(os.getenv('CONNECT_TIMEOUT', '30'))
    return config


CONFIG = load_config()


class UserIDAllocator:
    """
    Thread-safe allocator for unique user IDs within a worker.

    User ID space is partitioned across workers:
    - Worker 0 gets IDs: 1, worker_count+1, 2*worker_count+1, ...
    - Worker 1 gets IDs: 2, worker_count+2, 2*worker_count+2, ...
    """

    def __init__(self, worker_index: int, worker_count: int, user_pool_size: int):
        self.worker_index = worker_index
        self.worker_count = worker_count
        self.user_pool_size = user_pool_size
        self._counter = 0
        self._lock = threading.Lock()
        self._base_id = worker_index + 1

    def get_next_user_id(self) -> int:
        """Get the next unique user ID for this worker."""
        with self._lock:
            user_id = self._base_id + (self._counter * self.worker_count)
            self._counter += 1

            if user_id > self.user_pool_size:
                self._counter = 0
                user_id = self._base_id
                logger.warning(f"User ID wrapped around at worker {self.worker_index}")

            return user_id

    def get_user_count(self) -> int:
        """Get number of users allocated so far."""
        with self._lock:
            return self._counter


# Global user ID allocator
USER_ALLOCATOR: Optional[UserIDAllocator] = None


def get_user_allocator() -> UserIDAllocator:
    """Get or create the user ID allocator."""
    global USER_ALLOCATOR
    if USER_ALLOCATOR is None:
        USER_ALLOCATOR = UserIDAllocator(
            CONFIG.worker_index,
            CONFIG.worker_count,
            CONFIG.user_pool_size
        )
    return USER_ALLOCATOR


# Global asyncio event loop running in background thread
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_loop_lock = threading.Lock()


def get_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create the background asyncio event loop."""
    global _loop, _loop_thread

    with _loop_lock:
        if _loop is None or not _loop.is_running():
            _loop = asyncio.new_event_loop()

            def run_loop():
                asyncio.set_event_loop(_loop)
                _loop.run_forever()

            _loop_thread = threading.Thread(target=run_loop, daemon=True)
            _loop_thread.start()

            # Wait for loop to start
            while not _loop.is_running():
                time.sleep(0.01)

    return _loop


def run_async(coro):
    """Run an async coroutine from sync code and wait for result."""
    loop = get_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=CONFIG.connect_timeout + 5)


class GMQTTConnectionClient:
    """gmqtt-based MQTT client wrapper that tracks connection metrics."""

    def __init__(self, client_id: str, environment):
        self.client_id = client_id
        self.environment = environment
        self._connected = False
        self._connect_start: Optional[float] = None
        self._connect_error: Optional[str] = None
        self._connect_event: Optional[asyncio.Event] = None
        self.client: Optional[MQTTClient] = None

    async def _connect_async(self, broker: str, port: int, use_tls: bool) -> bool:
        """Async connection implementation."""
        self._connect_start = time.time()
        self._connect_error = None
        self._connect_event = asyncio.Event()

        try:
            # Create client
            self.client = MQTTClient(self.client_id)

            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect

            # Set credentials (username = client_id for auth-callout)
            self.client.set_auth_credentials(self.client_id, None)

            # Configure TLS
            ssl_context = None
            if use_tls:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            # Connect with timeout
            await asyncio.wait_for(
                self.client.connect(broker, port, ssl=ssl_context, version=MQTTv311),
                timeout=CONFIG.connect_timeout
            )

            # Wait for CONNACK
            try:
                await asyncio.wait_for(
                    self._connect_event.wait(),
                    timeout=CONFIG.connect_timeout
                )
            except asyncio.TimeoutError:
                raise Exception(f"CONNACK timeout ({CONFIG.connect_timeout}s)")

            if self._connected:
                return True
            elif self._connect_error:
                raise Exception(self._connect_error)
            else:
                raise Exception("Connection failed")

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
            return False

    def connect(self, broker: str, port: int, use_tls: bool = True) -> bool:
        """Connect to MQTT broker. Returns True if successful."""
        try:
            return run_async(self._connect_async(broker, port, use_tls))
        except Exception as e:
            response_time = (time.time() - (self._connect_start or time.time())) * 1000
            self.environment.events.request.fire(
                request_type="MQTT",
                name="connect",
                response_time=response_time,
                response_length=0,
                exception=e,
                context={"client_id": self.client_id}
            )
            return False

    def _on_connect(self, client, flags, rc, properties):
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

        # Signal that connection attempt is complete
        if self._connect_event:
            loop = get_event_loop()
            loop.call_soon_threadsafe(self._connect_event.set)

    def _on_disconnect(self, client, packet, exc=None):
        """Handle disconnection callback."""
        self._connected = False

    async def _disconnect_async(self):
        """Async disconnect implementation."""
        if self.client and self._connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self._connected = False

    def disconnect(self):
        """Disconnect from broker."""
        if self._connected and self.client:
            try:
                run_async(self._disconnect_async())
            except Exception:
                pass
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


class MQTTConnectionUser(User):
    """
    Locust user that connects to MQTT broker and maintains connection.

    Each user gets a unique client_id from the UserIDAllocator, ensuring
    no duplicates across workers in distributed mode.
    """

    # Longer wait time to reduce reconnection attempts
    wait_time = between(30, 60)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Get unique user ID from allocator
        allocator = get_user_allocator()
        user_num = allocator.get_next_user_id()
        self.client_id = f"{CONFIG.user_prefix}{user_num}"
        self.mqtt_client: Optional[GMQTTConnectionClient] = None

        # Parse broker from host
        self.broker = CONFIG.mqtt_broker
        self.port = CONFIG.mqtt_port

        if not self.broker and self.host:
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
        self.mqtt_client = GMQTTConnectionClient(self.client_id, self.environment)
        self.mqtt_client.connect(self.broker, self.port, self.use_tls)

    def on_stop(self):
        """Called when user stops - disconnect."""
        if self.mqtt_client:
            self.mqtt_client.disconnect()

    @task
    def maintain_connection(self):
        """Keep connection alive and reconnect if needed."""
        if not self.mqtt_client or not self.mqtt_client.is_connected:
            if self.mqtt_client:
                self.mqtt_client.disconnect()

            self.mqtt_client = GMQTTConnectionClient(self.client_id, self.environment)
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
    # Initialize the event loop
    get_event_loop()

    logger.info("=" * 60)
    logger.info("MQTT Distributed Load Test (gmqtt)")
    logger.info("=" * 60)
    logger.info(f"Worker: {CONFIG.worker_index + 1} of {CONFIG.worker_count}")
    logger.info(f"User pool: {CONFIG.user_prefix}1 to {CONFIG.user_prefix}{CONFIG.user_pool_size}")
    logger.info(f"User ID allocation: interleaved (worker gets every {CONFIG.worker_count}th ID)")
    logger.info(f"TLS enabled: {CONFIG.use_tls}")
    logger.info(f"Connect timeout: {CONFIG.connect_timeout}s")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    allocator = get_user_allocator()

    logger.info("=" * 60)
    logger.info("MQTT Distributed Load Test Complete")
    logger.info("=" * 60)
    logger.info(f"Worker {CONFIG.worker_index + 1} stats:")
    logger.info(f"  Users allocated: {allocator.get_user_count()}")
    with stats_lock:
        logger.info(f"  Total attempts: {connection_stats['total_attempts']}")
        logger.info(f"  Successful: {connection_stats['successful']}")
        logger.info(f"  Failed: {connection_stats['failed']}")
        logger.info(f"  Auth failures: {connection_stats['auth_failures']}")
        if connection_stats['total_attempts'] > 0:
            success_rate = connection_stats['successful'] / connection_stats['total_attempts'] * 100
            logger.info(f"  Success rate: {success_rate:.1f}%")
    logger.info("=" * 60)
