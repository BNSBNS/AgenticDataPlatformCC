"""
Kafka consumer wrapper with offset management and deserialization.

Provides reliable message consumption with flexible offset management,
automatic deserialization, and monitoring integration.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import json
import re

from kafka import KafkaConsumer, TopicPartition, OffsetAndMetadata
from kafka.errors import KafkaError

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
        config = {
            "bootstrap_servers": self.bootstrap_servers,
            "group_id": self.group_id,
            "client_id": self.client_id,
            "auto_offset_reset": self.auto_offset_reset,
            "enable_auto_commit": self.enable_auto_commit,
            "auto_commit_interval_ms": self.auto_commit_interval_ms,
            "max_poll_records": self.max_poll_records,
            "session_timeout_ms": self.session_timeout_ms,
            "heartbeat_interval_ms": self.heartbeat_interval_ms,
        }

        # Add deserializers
        if self.value_deserializer == "json":
            config["value_deserializer"] = lambda v: json.loads(v.decode("utf-8")) if v else None
        elif self.value_deserializer == "string":
            config["value_deserializer"] = lambda v: v.decode("utf-8") if v else None
        elif self.value_deserializer == "bytes":
            config["value_deserializer"] = lambda v: v

        if self.key_deserializer == "string":
            config["key_deserializer"] = lambda k: k.decode("utf-8") if k else None
        elif self.key_deserializer == "bytes":
            config["key_deserializer"] = lambda k: k

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
        self._consumer = KafkaConsumer(*config.topics, **kafka_config)

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
            # Poll for messages
            message_batch = self._consumer.poll(
                timeout_ms=timeout_ms,
                max_records=max_messages or self.config.max_poll_records,
            )

            messages = []

            for topic_partition, records in message_batch.items():
                for record in records:
                    message = {
                        "topic": record.topic,
                        "partition": record.partition,
                        "offset": record.offset,
                        "key": record.key,
                        "value": record.value,
                        "timestamp": record.timestamp,
                        "headers": dict(record.headers) if record.headers else {},
                    }
                    messages.append(message)

                    # Record metrics
                    kafka_messages_consumed_total.labels(
                        topic=record.topic,
                        group_id=self.config.group_id,
                        status="success",
                    ).inc()

                # Limit to max_messages if specified
                if max_messages and len(messages) >= max_messages:
                    break

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

    def commit(self, offsets: Optional[Dict[TopicPartition, OffsetAndMetadata]] = None):
        """
        Commit offsets.

        Args:
            offsets: Specific offsets to commit (None = commit current position)
        """
        try:
            if offsets:
                self._consumer.commit(offsets=offsets)
            else:
                self._consumer.commit()

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
        kafka_offsets = {}

        for (topic, partition), offset in offsets.items():
            tp = TopicPartition(topic, partition)
            kafka_offsets[tp] = OffsetAndMetadata(offset, None)

        self.commit(kafka_offsets)

    def seek(self, topic: str, partition: int, offset: int):
        """
        Seek to specific offset.

        Args:
            topic: Topic name
            partition: Partition number
            offset: Target offset
        """
        tp = TopicPartition(topic, partition)
        self._consumer.seek(tp, offset)
        logger.debug(f"Seeked to offset {offset} on {topic}:{partition}")

    def seek_to_beginning(self, partitions: Optional[List[TopicPartition]] = None):
        """
        Seek to beginning of partitions.

        Args:
            partitions: Specific partitions (None = all assigned)
        """
        if partitions:
            self._consumer.seek_to_beginning(*partitions)
        else:
            self._consumer.seek_to_beginning()

        logger.debug("Seeked to beginning")

    def seek_to_end(self, partitions: Optional[List[TopicPartition]] = None):
        """
        Seek to end of partitions.

        Args:
            partitions: Specific partitions (None = all assigned)
        """
        if partitions:
            self._consumer.seek_to_end(*partitions)
        else:
            self._consumer.seek_to_end()

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
        self._consumer.pause(*topic_partitions)
        logger.info(f"Paused {len(partitions)} partitions")

    def resume(self, partitions: List[Tuple[str, int]]):
        """
        Resume consumption from partitions.

        Args:
            partitions: List of (topic, partition) tuples
        """
        topic_partitions = [TopicPartition(t, p) for t, p in partitions]
        self._consumer.resume(*topic_partitions)
        logger.info(f"Resumed {len(partitions)} partitions")

    def get_partitions(self, topic: str) -> List[int]:
        """
        Get partition numbers for a topic.

        Args:
            topic: Topic name

        Returns:
            List of partition numbers
        """
        partitions = self._consumer.partitions_for_topic(topic)
        return list(partitions) if partitions else []

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

        beginning = self._consumer.beginning_offsets([tp])
        end = self._consumer.end_offsets([tp])

        return {
            "low": beginning[tp],
            "high": end[tp],
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get consumer metrics.

        Returns:
            Dictionary of metrics
        """
        try:
            return self._consumer.metrics()
        except Exception as e:
            logger.error(f"Failed to get consumer metrics: {e}")
            return {}

    def close(self, autocommit: bool = True):
        """
        Close consumer connection.

        Args:
            autocommit: Commit offsets on close
        """
        try:
            self._consumer.close(autocommit=autocommit)
            logger.info("Kafka consumer closed")

        except Exception as e:
            logger.error(f"Error closing consumer: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
