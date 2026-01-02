"""
Kafka producer wrapper with retry logic and serialization support.

Provides reliable message production with automatic retries, serialization,
and monitoring integration.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
import json
import time

from confluent_kafka import Producer, KafkaException
from confluent_kafka.error import KafkaError

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import KafkaProducerError
from src.common.metrics import (
    kafka_messages_produced_total,
    kafka_producer_errors_total,
    kafka_producer_latency_seconds,
)

logger = get_logger(__name__)


@dataclass
class ProducerConfig:
    """
    Configuration for Kafka producer.

    Attributes:
        bootstrap_servers: Kafka bootstrap servers
        client_id: Producer client ID
        acks: Acknowledgment mode (0, 1, 'all')
        retries: Number of retries
        compression_type: Compression codec
        batch_size: Batch size in bytes
        linger_ms: Linger time in milliseconds
        value_serializer: Serialization format (json, avro, string)
        key_serializer: Key serialization format
        max_request_size: Maximum request size
        transactional_id: Transaction ID for exactly-once semantics
        schema_registry_url: Schema registry URL for Avro
    """

    bootstrap_servers: str
    client_id: str = "dataplatform-producer"
    acks: Union[int, str] = "all"
    retries: int = 3
    compression_type: Optional[str] = None
    batch_size: int = 16384
    linger_ms: int = 0
    value_serializer: str = "json"
    key_serializer: str = "string"
    max_request_size: int = 1048576
    transactional_id: Optional[str] = None
    schema_registry_url: Optional[str] = None
    additional_config: Dict[str, Any] = field(default_factory=dict)

    def to_kafka_config(self) -> Dict[str, Any]:
        """
        Convert to Kafka producer configuration.

        Returns:
            Dictionary of Kafka configuration parameters
        """
        # confluent-kafka uses dot notation for config keys
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": self.client_id,
            "acks": str(self.acks),
            "retries": str(self.retries),
            "batch.size": str(self.batch_size),
            "linger.ms": str(self.linger_ms),
            "message.max.bytes": str(self.max_request_size),
        }

        if self.compression_type:
            config["compression.type"] = self.compression_type

        if self.transactional_id:
            config["transactional.id"] = self.transactional_id

        # Note: confluent-kafka doesn't use serializer functions in config
        # Serialization is handled at send time

        # Merge additional config
        config.update(self.additional_config)

        return config


class KafkaProducerManager:
    """
    Manages Kafka message production with reliability features.

    Provides message sending with automatic retries, serialization,
    and comprehensive error handling.
    """

    def __init__(self, config: ProducerConfig):
        """
        Initialize Kafka producer manager.

        Args:
            config: Producer configuration
        """
        self.config = config

        # Initialize Kafka producer
        kafka_config = config.to_kafka_config()
        self._producer = Producer(kafka_config)

        # Initialize transactions if configured
        if config.transactional_id:
            self._producer.init_transactions()

        logger.info(
            "Kafka producer initialized",
            client_id=config.client_id,
            bootstrap_servers=config.bootstrap_servers,
        )

    def send_message(
        self,
        topic: str,
        message: Any,
        key: Optional[str] = None,
        partition: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a message to Kafka topic.

        Args:
            topic: Target topic
            message: Message to send
            key: Message key for partitioning
            partition: Specific partition
            headers: Message headers
            max_retries: Override default retry count

        Returns:
            Dictionary with send result
        """
        start_time = time.time()
        result = {"success": False, "error": None}

        def delivery_callback(err, msg):
            """Callback for delivery reports."""
            nonlocal result
            latency = time.time() - start_time

            if err is not None:
                result["success"] = False
                result["error"] = str(err)
                kafka_messages_produced_total.labels(
                    topic=topic, status="error"
                ).inc()
                kafka_producer_errors_total.labels(
                    topic=topic, error_type="delivery_failed"
                ).inc()
                logger.error(f"Message delivery failed: {err}")
            else:
                result["success"] = True
                result["topic"] = msg.topic()
                result["partition"] = msg.partition()
                result["offset"] = msg.offset()
                result["timestamp"] = msg.timestamp()[1] if msg.timestamp()[0] != -1 else None

                kafka_messages_produced_total.labels(
                    topic=topic, status="success"
                ).inc()
                kafka_producer_latency_seconds.labels(topic=topic).observe(latency)

                logger.debug(
                    "Message sent successfully",
                    topic=msg.topic(),
                    partition=msg.partition(),
                    offset=msg.offset(),
                )

        try:
            # Serialize message based on config
            if self.config.value_serializer == "json":
                value = json.dumps(message).encode("utf-8")
            elif self.config.value_serializer == "string":
                value = str(message).encode("utf-8")
            else:
                value = message if isinstance(message, bytes) else str(message).encode("utf-8")

            # Serialize key
            key_bytes = None
            if key:
                if self.config.key_serializer == "string":
                    key_bytes = str(key).encode("utf-8")
                else:
                    key_bytes = key if isinstance(key, bytes) else str(key).encode("utf-8")

            # Prepare headers
            kafka_headers = None
            if headers:
                kafka_headers = [
                    (k, v.encode("utf-8") if isinstance(v, str) else v)
                    for k, v in headers.items()
                ]

            # Send message (asynchronous with callback)
            self._producer.produce(
                topic,
                value=value,
                key=key_bytes,
                partition=partition if partition is not None else -1,
                headers=kafka_headers,
                on_delivery=delivery_callback,
            )

            # Poll to trigger callback
            self._producer.poll(0)

            # Flush to wait for delivery
            self._producer.flush(timeout=10)

            return result

        except BufferError as e:
            # Queue is full, wait and retry
            logger.warning(f"Producer queue full, waiting: {e}")
            self._producer.poll(1)
            kafka_producer_errors_total.labels(
                topic=topic, error_type="buffer_full"
            ).inc()
            return {"success": False, "error": "Buffer full"}

        except Exception as e:
            logger.error(f"Failed to send message to {topic}: {e}")
            kafka_messages_produced_total.labels(topic=topic, status="error").inc()
            kafka_producer_errors_total.labels(
                topic=topic, error_type="send_failed"
            ).inc()
            return {"success": False, "error": str(e)}

    def send_batch(
        self,
        topic: str,
        messages: List[Any],
        keys: Optional[List[str]] = None,
        headers: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Send multiple messages in batch.

        Args:
            topic: Target topic
            messages: List of messages
            keys: List of keys (optional)
            headers: List of headers (optional)

        Returns:
            List of send results
        """
        results = []

        for i, message in enumerate(messages):
            key = keys[i] if keys and i < len(keys) else None
            header = headers[i] if headers and i < len(headers) else None

            result = self.send_message(topic, message, key=key, headers=header)
            results.append(result)

        logger.info(
            f"Sent batch of {len(messages)} messages",
            topic=topic,
            successful=sum(1 for r in results if r["success"]),
        )

        return results

    def flush(self, timeout: Optional[float] = None):
        """
        Flush pending messages.

        Args:
            timeout: Flush timeout in seconds
        """
        try:
            if timeout:
                self._producer.flush(timeout=timeout)
            else:
                self._producer.flush()

            logger.debug("Producer flushed successfully")

        except Exception as e:
            logger.error(f"Failed to flush producer: {e}")
            raise KafkaProducerError(f"Flush failed: {e}")

    def close(self, timeout: Optional[float] = None):
        """
        Close producer connection.

        Args:
            timeout: Close timeout in seconds
        """
        try:
            if timeout:
                self._producer.close(timeout=timeout)
            else:
                self._producer.close()

            logger.info("Kafka producer closed")

        except Exception as e:
            logger.error(f"Error closing producer: {e}")

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get producer metrics.

        Returns:
            Dictionary of metrics (length of outstanding messages queue)
        """
        try:
            # confluent-kafka doesn't have metrics() method
            # Return queue length instead
            return {
                "queue_length": len(self._producer),
            }
        except Exception as e:
            logger.error(f"Failed to get producer metrics: {e}")
            return {}

    def _serialize_json(self, data: Any) -> bytes:
        """
        Serialize data to JSON bytes.

        Args:
            data: Data to serialize

        Returns:
            JSON bytes
        """
        return json.dumps(data).encode("utf-8")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
