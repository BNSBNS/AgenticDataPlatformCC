"""
Unit tests for Kafka admin utilities.

Tests topic management, configuration, and monitoring capabilities.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List

from src.streaming.kafka.admin import KafkaAdminManager, TopicConfig


class TestKafkaAdminManager:
    """Test suite for Kafka admin operations."""

    @pytest.fixture
    def admin_manager(self):
        """Fixture for KafkaAdminManager instance."""
        with patch("src.streaming.kafka.admin.AdminClient"):
            manager = KafkaAdminManager(bootstrap_servers="localhost:9092")
            return manager

    def test_initialization(self, admin_manager):
        """Test that admin manager initializes correctly."""
        assert admin_manager is not None
        assert admin_manager.bootstrap_servers == "localhost:9092"

    def test_create_topic(self, admin_manager):
        """Test creating a new topic."""
        topic_config = TopicConfig(
            name="test-topic",
            num_partitions=3,
            replication_factor=2,
            retention_ms=604800000,  # 7 days
        )

        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_admin.create_topics.return_value = {
                "test-topic": MagicMock(result=lambda: None)
            }
            result = admin_manager.create_topic(topic_config)
            assert result is True

    def test_create_topic_already_exists(self, admin_manager):
        """Test creating a topic that already exists."""
        topic_config = TopicConfig(name="existing-topic", num_partitions=3)

        with patch.object(admin_manager, "_admin") as mock_admin:
            from kafka.errors import TopicAlreadyExistsError

            mock_admin.create_topics.return_value = {
                "existing-topic": MagicMock(
                    result=MagicMock(side_effect=TopicAlreadyExistsError("Topic exists"))
                )
            }
            result = admin_manager.create_topic(topic_config, skip_if_exists=True)
            assert result is True

    def test_delete_topic(self, admin_manager):
        """Test deleting a topic."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_admin.delete_topics.return_value = {
                "test-topic": MagicMock(result=lambda: None)
            }
            result = admin_manager.delete_topic("test-topic")
            assert result is True

    def test_list_topics(self, admin_manager):
        """Test listing all topics."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_metadata = Mock()
            mock_metadata.topics = {
                "topic1": Mock(),
                "topic2": Mock(),
                "__consumer_offsets": Mock(),
            }
            mock_admin.list_topics.return_value = mock_metadata

            topics = admin_manager.list_topics()
            assert "topic1" in topics
            assert "topic2" in topics
            assert "__consumer_offsets" not in topics  # Internal topics filtered

    def test_describe_topic(self, admin_manager):
        """Test describing topic configuration."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_metadata = Mock()
            mock_topic_metadata = Mock()
            mock_topic_metadata.partitions = {
                0: Mock(id=0, leader=1, replicas=[1, 2], isrs=[1, 2]),
                1: Mock(id=1, leader=2, replicas=[1, 2], isrs=[1, 2]),
            }
            mock_metadata.topics = {"test-topic": mock_topic_metadata}
            mock_admin.list_topics.return_value = mock_metadata

            topic_info = admin_manager.describe_topic("test-topic")
            assert topic_info["name"] == "test-topic"
            assert topic_info["num_partitions"] == 2
            assert len(topic_info["partitions"]) == 2

    def test_alter_topic_config(self, admin_manager):
        """Test altering topic configuration."""
        config_updates = {
            "retention.ms": "86400000",  # 1 day
            "compression.type": "snappy",
        }

        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_admin.alter_configs.return_value = {
                "test-topic": MagicMock(result=lambda: None)
            }
            result = admin_manager.alter_topic_config("test-topic", config_updates)
            assert result is True

    def test_get_topic_config(self, admin_manager):
        """Test retrieving topic configuration."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_config_resource = Mock()
            mock_config_resource.resources = [
                Mock(
                    configs={
                        "retention.ms": Mock(value="604800000"),
                        "compression.type": Mock(value="producer"),
                    }
                )
            ]
            mock_admin.describe_configs.return_value = mock_config_resource

            config = admin_manager.get_topic_config("test-topic")
            assert "retention.ms" in config
            assert config["retention.ms"] == "604800000"

    def test_topic_exists(self, admin_manager):
        """Test checking if topic exists."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_metadata = Mock()
            mock_metadata.topics = {"existing-topic": Mock()}
            mock_admin.list_topics.return_value = mock_metadata

            assert admin_manager.topic_exists("existing-topic") is True
            assert admin_manager.topic_exists("non-existing-topic") is False

    def test_get_consumer_groups(self, admin_manager):
        """Test listing consumer groups."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_admin.list_consumer_groups.return_value = [
                ("group1", "consumer"),
                ("group2", "consumer"),
            ]
            groups = admin_manager.get_consumer_groups()
            assert len(groups) == 2
            assert "group1" in groups

    def test_describe_consumer_group(self, admin_manager):
        """Test describing consumer group details."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_group_metadata = Mock()
            mock_group_metadata.members = [
                Mock(member_id="member1", client_id="client1"),
                Mock(member_id="member2", client_id="client2"),
            ]
            mock_group_metadata.state = "Stable"
            mock_admin.describe_consumer_groups.return_value = {
                "test-group": mock_group_metadata
            }

            group_info = admin_manager.describe_consumer_group("test-group")
            assert group_info["group_id"] == "test-group"
            assert group_info["state"] == "Stable"
            assert len(group_info["members"]) == 2

    def test_create_topics_batch(self, admin_manager):
        """Test creating multiple topics at once."""
        topic_configs = [
            TopicConfig(name="topic1", num_partitions=3),
            TopicConfig(name="topic2", num_partitions=6),
            TopicConfig(name="topic3", num_partitions=1),
        ]

        with patch.object(admin_manager, "_admin") as mock_admin:
            mock_admin.create_topics.return_value = {
                "topic1": MagicMock(result=lambda: None),
                "topic2": MagicMock(result=lambda: None),
                "topic3": MagicMock(result=lambda: None),
            }
            results = admin_manager.create_topics_batch(topic_configs)
            assert len(results) == 3
            assert all(results.values())

    def test_get_topic_offsets(self, admin_manager):
        """Test retrieving topic offset information."""
        with patch.object(admin_manager, "_admin") as mock_admin:
            # Mock consumer for offset retrieval
            mock_consumer = Mock()
            mock_consumer.beginning_offsets.return_value = {
                Mock(topic="test-topic", partition=0): 0,
                Mock(topic="test-topic", partition=1): 0,
            }
            mock_consumer.end_offsets.return_value = {
                Mock(topic="test-topic", partition=0): 1000,
                Mock(topic="test-topic", partition=1): 2000,
            }

            with patch("src.streaming.kafka.admin.KafkaConsumer", return_value=mock_consumer):
                offsets = admin_manager.get_topic_offsets("test-topic")
                assert len(offsets) == 2
                assert all("earliest" in offset and "latest" in offset for offset in offsets.values())


class TestTopicConfig:
    """Test suite for TopicConfig data class."""

    def test_topic_config_defaults(self):
        """Test TopicConfig with default values."""
        config = TopicConfig(name="test-topic")
        assert config.name == "test-topic"
        assert config.num_partitions == 1
        assert config.replication_factor == 1
        assert config.config == {}

    def test_topic_config_custom_values(self):
        """Test TopicConfig with custom values."""
        custom_config = {
            "retention.ms": "604800000",
            "compression.type": "snappy",
        }
        config = TopicConfig(
            name="custom-topic",
            num_partitions=6,
            replication_factor=3,
            retention_ms=604800000,
            compression_type="snappy",
            config=custom_config,
        )
        assert config.name == "custom-topic"
        assert config.num_partitions == 6
        assert config.replication_factor == 3
        assert config.retention_ms == 604800000
        assert config.compression_type == "snappy"

    def test_topic_config_to_kafka_config(self):
        """Test converting TopicConfig to Kafka configuration dict."""
        config = TopicConfig(
            name="test-topic",
            retention_ms=86400000,
            compression_type="lz4",
            min_insync_replicas=2,
        )
        kafka_config = config.to_kafka_config()
        assert kafka_config["retention.ms"] == "86400000"
        assert kafka_config["compression.type"] == "lz4"
        assert kafka_config["min.insync.replicas"] == "2"
