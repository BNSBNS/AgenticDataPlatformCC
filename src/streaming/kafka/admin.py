"""
Kafka admin utilities for topic management.

Provides functionality for creating, deleting, and managing Kafka topics
and consumer groups.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import time

from confluent_kafka.admin import (
    AdminClient,
    NewTopic,
    ConfigResource,
    ResourceType,
)
from confluent_kafka import KafkaException, Consumer
from confluent_kafka.error import KafkaError

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import KafkaAdminError
from src.common.metrics import kafka_admin_operations_total

logger = get_logger(__name__)


@dataclass
class TopicConfig:
    """
    Configuration for a Kafka topic.

    Attributes:
        name: Topic name
        num_partitions: Number of partitions
        replication_factor: Replication factor
        retention_ms: Retention period in milliseconds
        compression_type: Compression codec
        min_insync_replicas: Minimum in-sync replicas
        config: Additional topic-level configuration
    """

    name: str
    num_partitions: int = 1
    replication_factor: int = 1
    retention_ms: Optional[int] = None
    compression_type: Optional[str] = None
    min_insync_replicas: Optional[int] = None
    config: Dict[str, str] = field(default_factory=dict)

    def to_kafka_config(self) -> Dict[str, str]:
        """
        Convert to Kafka topic configuration dictionary.

        Returns:
            Dictionary of Kafka configuration parameters
        """
        kafka_config = self.config.copy()

        if self.retention_ms is not None:
            kafka_config["retention.ms"] = str(self.retention_ms)

        if self.compression_type is not None:
            kafka_config["compression.type"] = self.compression_type

        if self.min_insync_replicas is not None:
            kafka_config["min.insync.replicas"] = str(self.min_insync_replicas)

        return kafka_config


class KafkaAdminManager:
    """
    Manages Kafka administrative operations.

    Provides methods for topic management, consumer group monitoring,
    and cluster configuration.
    """

    def __init__(self, bootstrap_servers: Optional[str] = None):
        """
        Initialize Kafka admin manager.

        Args:
            bootstrap_servers: Kafka bootstrap servers
        """
        self.config = get_config()
        self.bootstrap_servers = bootstrap_servers or self.config.kafka_bootstrap_servers

        # Initialize admin client
        self._admin = AdminClient(
            {
                "bootstrap.servers": self.bootstrap_servers,
                "client.id": "dataplatform-admin",
            }
        )

        logger.info(
            "Kafka admin manager initialized",
            bootstrap_servers=self.bootstrap_servers,
        )

    def create_topic(
        self,
        topic_config: TopicConfig,
        skip_if_exists: bool = True,
        timeout: float = 30.0,
    ) -> bool:
        """
        Create a Kafka topic.

        Args:
            topic_config: Topic configuration
            skip_if_exists: Skip creation if topic exists
            timeout: Operation timeout in seconds

        Returns:
            True if topic was created, False if skipped

        Raises:
            KafkaAdminError: If topic creation fails
        """
        try:
            logger.info(
                "Creating Kafka topic",
                topic=topic_config.name,
                partitions=topic_config.num_partitions,
                replication=topic_config.replication_factor,
            )

            new_topic = NewTopic(
                topic=topic_config.name,
                num_partitions=topic_config.num_partitions,
                replication_factor=topic_config.replication_factor,
                config=topic_config.to_kafka_config(),
            )

            future_map = self._admin.create_topics([new_topic])

            # Wait for operation to complete
            for topic_name, future in future_map.items():
                try:
                    future.result(timeout=timeout)
                    logger.info("Topic created successfully", topic=topic_name)
                    kafka_admin_operations_total.labels(
                        operation="create_topic", status="success"
                    ).inc()
                    return True
                except KafkaException as ke:
                    # Check if topic already exists
                    if ke.args[0].code() == KafkaError.TOPIC_ALREADY_EXISTS:
                        if skip_if_exists:
                            logger.info("Topic already exists, skipping", topic=topic_name)
                            return True
                        else:
                            raise KafkaAdminError(f"Topic {topic_name} already exists")
                    else:
                        raise

        except Exception as e:
            logger.error(f"Failed to create topic {topic_config.name}: {e}")
            kafka_admin_operations_total.labels(
                operation="create_topic", status="error"
            ).inc()
            raise KafkaAdminError(f"Topic creation failed: {e}")

    def delete_topic(self, topic_name: str, timeout: float = 30.0) -> bool:
        """
        Delete a Kafka topic.

        Args:
            topic_name: Name of topic to delete
            timeout: Operation timeout in seconds

        Returns:
            True if topic was deleted

        Raises:
            KafkaAdminError: If topic deletion fails
        """
        try:
            logger.info("Deleting Kafka topic", topic=topic_name)

            future_map = self._admin.delete_topics([topic_name])

            for topic, future in future_map.items():
                try:
                    future.result(timeout=timeout)
                    logger.info("Topic deleted successfully", topic=topic)
                    kafka_admin_operations_total.labels(
                        operation="delete_topic", status="success"
                    ).inc()
                    return True
                except KafkaException as ke:
                    # Check if topic doesn't exist
                    if ke.args[0].code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                        logger.warning("Topic does not exist", topic=topic)
                        return False
                    else:
                        raise

        except Exception as e:
            logger.error(f"Failed to delete topic {topic_name}: {e}")
            kafka_admin_operations_total.labels(
                operation="delete_topic", status="error"
            ).inc()
            raise KafkaAdminError(f"Topic deletion failed: {e}")

    def list_topics(self, exclude_internal: bool = True) -> List[str]:
        """
        List all Kafka topics.

        Args:
            exclude_internal: Exclude internal topics (starting with __)

        Returns:
            List of topic names
        """
        try:
            metadata = self._admin.list_topics(timeout=10)
            topics = list(metadata.topics.keys())

            if exclude_internal:
                topics = [t for t in topics if not t.startswith("__")]

            logger.debug(f"Listed {len(topics)} topics")
            return topics

        except Exception as e:
            logger.error(f"Failed to list topics: {e}")
            raise KafkaAdminError(f"Failed to list topics: {e}")

    def topic_exists(self, topic_name: str) -> bool:
        """
        Check if a topic exists.

        Args:
            topic_name: Topic name to check

        Returns:
            True if topic exists
        """
        topics = self.list_topics(exclude_internal=False)
        return topic_name in topics

    def describe_topic(self, topic_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a topic.

        Args:
            topic_name: Topic name

        Returns:
            Dictionary with topic information

        Raises:
            KafkaAdminError: If topic doesn't exist
        """
        try:
            metadata = self._admin.list_topics(topic=topic_name, timeout=10)

            if topic_name not in metadata.topics:
                raise KafkaAdminError(f"Topic {topic_name} not found")

            topic_metadata = metadata.topics[topic_name]

            partitions_info = []
            for partition_id, partition_metadata in topic_metadata.partitions.items():
                partitions_info.append(
                    {
                        "partition": partition_id,
                        "leader": partition_metadata.leader,
                        "replicas": partition_metadata.replicas,
                        "isrs": partition_metadata.isrs,
                    }
                )

            return {
                "name": topic_name,
                "num_partitions": len(topic_metadata.partitions),
                "partitions": partitions_info,
            }

        except Exception as e:
            logger.error(f"Failed to describe topic {topic_name}: {e}")
            raise KafkaAdminError(f"Failed to describe topic: {e}")

    def get_topic_config(self, topic_name: str) -> Dict[str, str]:
        """
        Get configuration for a topic.

        Args:
            topic_name: Topic name

        Returns:
            Dictionary of configuration parameters
        """
        try:
            resource = ConfigResource(ResourceType.TOPIC, topic_name)
            futures = self._admin.describe_configs([resource])

            configs = {}
            # Wait for the future to complete
            for future in futures.values():
                config_resource = future.result()
                for config_name, config_entry in config_resource.items():
                    configs[config_name] = config_entry.value

            return configs

        except Exception as e:
            logger.error(f"Failed to get config for topic {topic_name}: {e}")
            raise KafkaAdminError(f"Failed to get topic config: {e}")

    def alter_topic_config(
        self, topic_name: str, config_updates: Dict[str, str], timeout: float = 30.0
    ) -> bool:
        """
        Update configuration for a topic.

        Args:
            topic_name: Topic name
            config_updates: Configuration updates
            timeout: Operation timeout

        Returns:
            True if configuration was updated
        """
        try:
            logger.info(
                "Updating topic configuration",
                topic=topic_name,
                updates=config_updates,
            )

            resource = ConfigResource(
                ResourceType.TOPIC, topic_name, set_config=config_updates
            )

            future_map = self._admin.alter_configs([resource])

            for resource, future in future_map.items():
                future.result(timeout=timeout)
                logger.info("Topic configuration updated", topic=topic_name)
                return True

        except Exception as e:
            logger.error(f"Failed to alter config for topic {topic_name}: {e}")
            raise KafkaAdminError(f"Failed to alter topic config: {e}")

    def create_topics_batch(
        self, topic_configs: List[TopicConfig], skip_if_exists: bool = True
    ) -> Dict[str, bool]:
        """
        Create multiple topics in batch.

        Args:
            topic_configs: List of topic configurations
            skip_if_exists: Skip topics that already exist

        Returns:
            Dictionary mapping topic names to success status
        """
        results = {}

        for topic_config in topic_configs:
            try:
                result = self.create_topic(topic_config, skip_if_exists)
                results[topic_config.name] = result
            except Exception as e:
                logger.error(f"Failed to create topic {topic_config.name}: {e}")
                results[topic_config.name] = False

        return results

    def get_consumer_groups(self) -> List[str]:
        """
        List all consumer groups.

        Returns:
            List of consumer group IDs
        """
        try:
            groups = self._admin.list_consumer_groups(timeout=10)
            return [group[0] for group in groups]

        except Exception as e:
            logger.error(f"Failed to list consumer groups: {e}")
            raise KafkaAdminError(f"Failed to list consumer groups: {e}")

    def describe_consumer_group(self, group_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a consumer group.

        Args:
            group_id: Consumer group ID

        Returns:
            Dictionary with consumer group information
        """
        try:
            groups = self._admin.describe_consumer_groups([group_id], timeout=10)

            if group_id not in groups:
                raise KafkaAdminError(f"Consumer group {group_id} not found")

            group_metadata = groups[group_id]

            members_info = []
            for member in group_metadata.members:
                members_info.append(
                    {
                        "member_id": member.member_id,
                        "client_id": member.client_id,
                    }
                )

            return {
                "group_id": group_id,
                "state": group_metadata.state,
                "members": members_info,
            }

        except Exception as e:
            logger.error(f"Failed to describe consumer group {group_id}: {e}")
            raise KafkaAdminError(f"Failed to describe consumer group: {e}")

    def get_topic_offsets(self, topic_name: str) -> Dict[int, Dict[str, int]]:
        """
        Get offset information for all partitions of a topic.

        Args:
            topic_name: Topic name

        Returns:
            Dictionary mapping partition to offset info
        """
        try:
            from confluent_kafka import TopicPartition, OFFSET_BEGINNING, OFFSET_END

            # Create temporary consumer to get offsets
            consumer = Consumer({
                'bootstrap.servers': self.bootstrap_servers,
                'group.id': f"admin-offset-check-{int(time.time())}",
                'enable.auto.commit': False,
            })

            # Get metadata for topic
            metadata = self._admin.list_topics(topic=topic_name, timeout=10)

            if topic_name not in metadata.topics:
                raise KafkaAdminError(f"Topic {topic_name} not found")

            topic_metadata = metadata.topics[topic_name]
            partitions = list(topic_metadata.partitions.keys())

            # Build offset info
            offset_info = {}
            for partition_id in partitions:
                # Get earliest offset
                tp_beginning = TopicPartition(topic_name, partition_id, OFFSET_BEGINNING)
                low_offset, high_offset = consumer.get_watermark_offsets(
                    TopicPartition(topic_name, partition_id),
                    timeout=10
                )

                offset_info[partition_id] = {
                    "earliest": low_offset,
                    "latest": high_offset,
                }

            consumer.close()
            return offset_info

        except Exception as e:
            logger.error(f"Failed to get offsets for topic {topic_name}: {e}")
            raise KafkaAdminError(f"Failed to get topic offsets: {e}")
