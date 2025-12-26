"""
Kafka consumer wrapper with offset management and deserialization.

Provides reliable message consumption with flexible offset management,
automatic deserialization, and monitoring integration.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import json
import re

from confluent_kafka import Consumer, TopicPartition, KafkaException, OFFSET_BEGINNING, OFFSET_END
from confluent_kafka.error import KafkaError

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import KafkaConsumerError
from src.common.metrics import (
    kafka_messages_consumed_total,
    kafka_consumer_errors_total,
    kafka_consumer_lag,
)

logger = get_logger(__name__)


@dataclass
class ConsumerConfig:
    """
    Configuration for Kafka consumer.

    Attributes:
        bootstrap_servers: Kafka bootstrap servers
        group_id: Consumer group ID
        topics: List of topics to subscribe
        client_id: Consumer client ID
        auto_offset_reset: Offset reset strategy (earliest, latest)
        enable_auto_commit: Enable automatic offset commits
        auto_commit_interval_ms: Auto commit interval
        max_poll_records: Maximum records per poll
        session_timeout_ms: Session timeout
        heartbeat_interval_ms: Heartbeat interval
        value_deserializer: Deserialization format (json, string, bytes)
        key_deserializer: Key deserialization format
    """

    bootstrap_servers: str
    group_id: str
    topics: List[str]
    client_id: str = "dataplatform-consumer"
    auto_offset_reset: str = "latest"
    enable_auto_commit: bool = True
    auto_commit_interval_ms: int = 5000
    max_poll_records: int = 500
    session_timeout_ms: int = 10000
    heartbeat_interval_ms: int = 3000
    value_deserializer: str = "json"
    key_deserializer: str = "string"
    additional_config: Dict[str, Any] = field(default_factory=dict)

    def to_kafka_config(self) -> Dict[str, Any]:
        """
        Convert to Kafka consumer configuration.

        Returns:
            Dictionary of Kafka configuration parameters
        """
        # confluent-kafka uses dot notation for config keys
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.group_id,
            "client.id": self.client_id,
            "auto.offset.reset": self.auto_offset_reset,
            "enable.auto.commit": str(self.enable_auto_commit).lower(),
            "auto.commit.interval.ms": str(self.auto_commit_interval_ms),
            "session.timeout.ms": str(self.session_timeout_ms),
            "heartbeat.interval.ms": str(self.heartbeat_interval_ms),
        }

        # Note: confluent-kafka doesn't use deserializer functions in config
        # Deserialization is handled when processing messages

        # Merge additional config
        config.update(self.additional_config)

        return config


class KafkaConsumerManager:
    """
    Manages Kafka message consumption with reliability features.

    Provides message consumption with flexible offset management,
    deserialization, and comprehensive error handling.
    """

    def __init__(self, config: ConsumerConfig):
        """
        Initialize Kafka consumer manager.

        Args:
            config: Consumer configuration
        """
        self.config = config

        # Initialize Kafka consumer
        kafka_config = config.to_kafka_config()
        self._consumer = Consumer(kafka_config)

        # Subscribe to topics
        if config.topics:
            self._consumer.subscribe(config.topics)

        logger.info(
            "Kafka consumer initialized",
            group_id=config.group_id,
            topics=config.topics,
            bootstrap_servers=config.bootstrap_servers,
        )

    def subscribe(self, topics: List[str]):
        """
        Subscribe to topics.

        Args:
            topics: List of topic names
        """
        self._consumer.subscribe(topics)
        logger.info(f"Subscribed to topics: {topics}")

    def subscribe_pattern(self, pattern: str):
        """
        Subscribe using topic pattern.

        Args:
            pattern: Regex pattern for topic names
        """
        self._consumer.subscribe(pattern=re.compile(pattern))
        logger.info(f"Subscribed to topic pattern: {pattern}")

    def consume(
        self,
        timeout_ms: int = 1000,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Consume messages from subscribed topics.

        Args:
            timeout_ms: Poll timeout in milliseconds
            max_messages: Maximum messages to consume

        Returns:
            List of consumed messages
        """
        try:
            messages = []
            max_msgs = max_messages or self.config.max_poll_records
            timeout_seconds = timeout_ms / 1000.0

            # Poll for messages (confluent-kafka polls one message at a time)
            while len(messages) < max_msgs:
                msg = self._consumer.poll(timeout=timeout_seconds)

                if msg is None:
                    # No more messages within timeout
                    break

                if msg.error():
                    # Handle error
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition - not an error
                        logger.debug(f"Reached end of partition: {msg.topic()}[{msg.partition()}]")
                        continue
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                        kafka_consumer_errors_total.labels(
                            group_id=self.config.group_id,
                            error_type="poll_error",
                        ).inc()
                        continue

                # Deserialize based on config
                value = msg.value()
                if value and self.config.value_deserializer == "json":
                    try:
                        value = json.loads(value.decode("utf-8"))
                    except:
                        pass
                elif value and self.config.value_deserializer == "string":
                    value = value.decode("utf-8")

                key = msg.key()
                if key and self.config.key_deserializer == "string":
                    key = key.decode("utf-8")

                # Build message dict
                message = {
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "key": key,
                    "value": value,
                    "timestamp": msg.timestamp()[1] if msg.timestamp()[0] != -1 else None,
                    "headers": dict(msg.headers()) if msg.headers() else {},
                }
                messages.append(message)

                # Record metrics
                kafka_messages_consumed_total.labels(
                    topic=msg.topic(),
                    group_id=self.config.group_id,
                    status="success",
                ).inc()

            if messages:
                logger.debug(f"Consumed {len(messages)} messages")

            return messages

        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
            kafka_consumer_errors_total.labels(
                group_id=self.config.group_id,
                error_type="consume_failed",
            ).inc()
            return []

    def commit(self, offsets: Optional[List[TopicPartition]] = None):
        """
        Commit offsets.

        Args:
            offsets: Specific offsets to commit (None = commit current position)
        """
        try:
            if offsets:
                self._consumer.commit(offsets=offsets, asynchronous=False)
            else:
                self._consumer.commit(asynchronous=False)

            logger.debug("Offsets committed successfully")

        except Exception as e:
            logger.error(f"Failed to commit offsets: {e}")
            raise KafkaConsumerError(f"Offset commit failed: {e}")

    def commit_offsets(self, offsets: Dict[Tuple[str, int], int]):
        """
        Commit specific offsets.

        Args:
            offsets: Dictionary mapping (topic, partition) to offset
        """
        kafka_offsets = []

        for (topic, partition), offset in offsets.items():
            # confluent-kafka uses offset+1 for commit (next message to read)
            tp = TopicPartition(topic, partition, offset + 1)
            kafka_offsets.append(tp)

        self.commit(kafka_offsets)

    def seek(self, topic: str, partition: int, offset: int):
        """
        Seek to specific offset.

        Args:
            topic: Topic name
            partition: Partition number
            offset: Target offset
        """
        tp = TopicPartition(topic, partition, offset)
        self._consumer.seek(tp)
        logger.debug(f"Seeked to offset {offset} on {topic}:{partition}")

    def seek_to_beginning(self, partitions: Optional[List[TopicPartition]] = None):
        """
        Seek to beginning of partitions.

        Args:
            partitions: Specific partitions (None = all assigned)
        """
        if not partitions:
            # Get assigned partitions
            partitions = self._consumer.assignment()

        for tp in partitions:
            tp_beginning = TopicPartition(tp.topic, tp.partition, OFFSET_BEGINNING)
            self._consumer.seek(tp_beginning)

        logger.debug("Seeked to beginning")

    def seek_to_end(self, partitions: Optional[List[TopicPartition]] = None):
        """
        Seek to end of partitions.

        Args:
            partitions: Specific partitions (None = all assigned)
        """
        if not partitions:
            # Get assigned partitions
            partitions = self._consumer.assignment()

        for tp in partitions:
            tp_end = TopicPartition(tp.topic, tp.partition, OFFSET_END)
            self._consumer.seek(tp_end)

        logger.debug("Seeked to end")

    def get_offsets(self) -> Dict[Tuple[str, int], int]:
        """
        Get current offsets for assigned partitions.

        Returns:
            Dictionary mapping (topic, partition) to offset
        """
        offsets = {}

        for partition in self._consumer.assignment():
            offset = self._consumer.position(partition)
            offsets[(partition.topic, partition.partition)] = offset

        return offsets

    def pause(self, partitions: List[Tuple[str, int]]):
        """
        Pause consumption from partitions.

        Args:
            partitions: List of (topic, partition) tuples
        """
        topic_partitions = [TopicPartition(t, p) for t, p in partitions]
        self._consumer.pause(topic_partitions)
        logger.info(f"Paused {len(partitions)} partitions")

    def resume(self, partitions: List[Tuple[str, int]]):
        """
        Resume consumption from partitions.

        Args:
            partitions: List of (topic, partition) tuples
        """
        topic_partitions = [TopicPartition(t, p) for t, p in partitions]
        self._consumer.resume(topic_partitions)
        logger.info(f"Resumed {len(partitions)} partitions")

    def get_partitions(self, topic: str) -> List[int]:
        """
        Get partition numbers for a topic.

        Args:
            topic: Topic name

        Returns:
            List of partition numbers
        """
        metadata = self._consumer.list_topics(topic=topic, timeout=10)
        if topic in metadata.topics:
            return list(metadata.topics[topic].partitions.keys())
        return []

    def get_watermarks(self, topic: str, partition: int) -> Dict[str, int]:
        """
        Get high and low watermarks for a partition.

        Args:
            topic: Topic name
            partition: Partition number

        Returns:
            Dictionary with 'low' and 'high' watermarks
        """
        tp = TopicPartition(topic, partition)
        low, high = self._consumer.get_watermark_offsets(tp, timeout=10)

        return {
            "low": low,
            "high": high,
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get consumer metrics.

        Returns:
            Dictionary of metrics (assignment info)
        """
        try:
            assignment = self._consumer.assignment()
            return {
                "assigned_partitions": len(assignment) if assignment else 0,
                "partitions": [
                    {"topic": tp.topic, "partition": tp.partition}
                    for tp in assignment
                ] if assignment else [],
            }
        except Exception as e:
            logger.error(f"Failed to get consumer metrics: {e}")
            return {}

    def close(self, autocommit: bool = True):
        """
        Close consumer connection.

        Args:
            autocommit: Commit offsets on close (ignored in confluent-kafka, always commits if auto-commit enabled)
        """
        try:
            self._consumer.close()
            logger.info("Kafka consumer closed")

        except Exception as e:
            logger.error(f"Error closing consumer: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
