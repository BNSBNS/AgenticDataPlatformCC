"""
Kafka producer wrapper with retry logic and serialization support.

Provides reliable message production with automatic retries, serialization,
and monitoring integration.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
import json
import time

from kafka import KafkaProducer
from kafka.errors import KafkaError, KafkaTimeoutError

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
        config = {
            "bootstrap_servers": self.bootstrap_servers,
            "client_id": self.client_id,
            "acks": self.acks,
            "retries": self.retries,
            "batch_size": self.batch_size,
            "linger_ms": self.linger_ms,
            "max_request_size": self.max_request_size,
        }

        if self.compression_type:
            config["compression_type"] = self.compression_type

        if self.transactional_id:
            config["transactional_id"] = self.transactional_id

        # Add serializers
        if self.value_serializer == "json":
            config["value_serializer"] = lambda v: json.dumps(v).encode("utf-8")
        elif self.value_serializer == "string":
            config["value_serializer"] = lambda v: str(v).encode("utf-8")

        if self.key_serializer == "string":
            config["key_serializer"] = lambda k: str(k).encode("utf-8") if k else None

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
        self._producer = KafkaProducer(**kafka_config)

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
        retries = max_retries or self.config.retries
        attempt = 0
        last_error = None

        start_time = time.time()

        while attempt <= retries:
            try:
                # Prepare headers
                kafka_headers = None
                if headers:
                    kafka_headers = [
                        (k, v.encode("utf-8")) for k, v in headers.items()
                    ]

                # Send message
                future = self._producer.send(
                    topic,
                    value=message,
                    key=key,
                    partition=partition,
                    headers=kafka_headers,
                )

                # Wait for result
                record_metadata = future.get(timeout=10)

                # Record metrics
                latency = time.time() - start_time
                kafka_messages_produced_total.labels(
                    topic=topic, status="success"
                ).inc()
                kafka_producer_latency_seconds.labels(topic=topic).observe(latency)

                logger.debug(
                    "Message sent successfully",
                    topic=topic,
                    partition=record_metadata.partition,
                    offset=record_metadata.offset,
                )

                return {
                    "success": True,
                    "topic": record_metadata.topic,
                    "partition": record_metadata.partition,
                    "offset": record_metadata.offset,
                    "timestamp": record_metadata.timestamp,
                }

            except KafkaTimeoutError as e:
                last_error = e
                attempt += 1
                if attempt <= retries:
                    logger.warning(
                        f"Send timeout, retrying ({attempt}/{retries})",
                        topic=topic,
                    )
                    time.sleep(0.1 * attempt)  # Exponential backoff
            except Exception as e:
                last_error = e
                logger.error(f"Failed to send message to {topic}: {e}")
                break

        # All retries exhausted
        kafka_messages_produced_total.labels(topic=topic, status="error").inc()
        kafka_producer_errors_total.labels(topic=topic, error_type="send_failed").inc()

        return {
            "success": False,
            "error": str(last_error),
            "attempts": attempt,
        }

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
            Dictionary of metrics
        """
        try:
            return self._producer.metrics()
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
