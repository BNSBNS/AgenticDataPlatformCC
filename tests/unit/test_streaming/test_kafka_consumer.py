"""
Unit tests for Kafka consumer wrapper.

Tests message consumption, offset management, and consumer groups.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig


class TestKafkaConsumerManager:
    """Test suite for Kafka consumer operations."""

    @pytest.fixture
    def consumer_config(self):
        """Fixture for consumer configuration."""
        return ConsumerConfig(
            bootstrap_servers="localhost:9092",
            group_id="test-consumer-group",
            topics=["test-topic"],
            auto_offset_reset="earliest",
        )

    @pytest.fixture
    def consumer_manager(self, consumer_config):
        """Fixture for KafkaConsumerManager instance."""
        with patch("src.streaming.kafka.consumer.KafkaConsumer"):
            manager = KafkaConsumerManager(consumer_config)
            return manager

    def test_initialization(self, consumer_manager, consumer_config):
        """Test that consumer manager initializes correctly."""
        assert consumer_manager is not None
        assert consumer_manager.config == consumer_config

    def test_subscribe_topics(self, consumer_manager):
        """Test subscribing to topics."""
        topics = ["topic1", "topic2", "topic3"]

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.subscribe(topics)
            mock_consumer.subscribe.assert_called_once_with(topics)

    def test_subscribe_pattern(self, consumer_manager):
        """Test subscribing using pattern."""
        pattern = "^events-.*"

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.subscribe_pattern(pattern)
            mock_consumer.subscribe.assert_called_once()

    def test_consume_messages(self, consumer_manager):
        """Test consuming messages from topic."""
        mock_messages = [
            Mock(
                topic="test-topic",
                partition=0,
                offset=10,
                key=b"key1",
                value=b'{"id": 1, "data": "test1"}',
                timestamp=1234567890000,
            ),
            Mock(
                topic="test-topic",
                partition=0,
                offset=11,
                key=b"key2",
                value=b'{"id": 2, "data": "test2"}',
                timestamp=1234567891000,
            ),
        ]

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_consumer.poll.return_value = {
                Mock(topic="test-topic", partition=0): mock_messages
            }

            messages = consumer_manager.consume(timeout_ms=1000, max_messages=10)

            assert len(messages) == 2
            assert messages[0]["offset"] == 10
            assert messages[1]["offset"] == 11

    def test_consume_with_deserialization(self, consumer_manager):
        """Test consuming messages with automatic deserialization."""
        mock_message = Mock(
            topic="test-topic",
            partition=0,
            offset=5,
            key=b"key1",
            value=b'{"id": 1, "name": "test", "value": 100}',
            timestamp=1234567890000,
        )

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_consumer.poll.return_value = {
                Mock(topic="test-topic", partition=0): [mock_message]
            }

            messages = consumer_manager.consume(timeout_ms=1000)

            assert len(messages) == 1
            assert isinstance(messages[0]["value"], dict)
            assert messages[0]["value"]["id"] == 1

    def test_commit_offsets(self, consumer_manager):
        """Test committing offsets."""
        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.commit()
            mock_consumer.commit.assert_called_once()

    def test_commit_specific_offsets(self, consumer_manager):
        """Test committing specific offsets."""
        offsets = {
            ("test-topic", 0): 100,
            ("test-topic", 1): 200,
        }

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.commit_offsets(offsets)
            mock_consumer.commit.assert_called_once()

    def test_seek_to_beginning(self, consumer_manager):
        """Test seeking to beginning of partitions."""
        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_partition = Mock(topic="test-topic", partition=0)
            mock_consumer.assignment.return_value = [mock_partition]

            consumer_manager.seek_to_beginning()

            mock_consumer.seek_to_beginning.assert_called_once()

    def test_seek_to_end(self, consumer_manager):
        """Test seeking to end of partitions."""
        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_partition = Mock(topic="test-topic", partition=0)
            mock_consumer.assignment.return_value = [mock_partition]

            consumer_manager.seek_to_end()

            mock_consumer.seek_to_end.assert_called_once()

    def test_seek_to_offset(self, consumer_manager):
        """Test seeking to specific offset."""
        topic = "test-topic"
        partition = 0
        offset = 500

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.seek(topic, partition, offset)
            mock_consumer.seek.assert_called_once()

    def test_get_offsets(self, consumer_manager):
        """Test retrieving current offsets."""
        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_partition = Mock(topic="test-topic", partition=0)
            mock_consumer.assignment.return_value = [mock_partition]
            mock_consumer.position.return_value = 150

            offsets = consumer_manager.get_offsets()

            assert len(offsets) > 0

    def test_pause_partitions(self, consumer_manager):
        """Test pausing consumption from partitions."""
        partitions = [("test-topic", 0), ("test-topic", 1)]

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.pause(partitions)
            mock_consumer.pause.assert_called_once()

    def test_resume_partitions(self, consumer_manager):
        """Test resuming consumption from partitions."""
        partitions = [("test-topic", 0), ("test-topic", 1)]

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.resume(partitions)
            mock_consumer.resume.assert_called_once()

    def test_close(self, consumer_manager):
        """Test closing consumer connection."""
        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            consumer_manager.close()
            mock_consumer.close.assert_called_once()

    def test_context_manager(self, consumer_config):
        """Test using consumer as context manager."""
        with patch("src.streaming.kafka.consumer.KafkaConsumer") as mock_consumer_class:
            mock_consumer = MagicMock()
            mock_consumer_class.return_value = mock_consumer

            with KafkaConsumerManager(consumer_config) as consumer:
                assert consumer is not None

            mock_consumer.close.assert_called_once()

    def test_consume_with_error_handling(self, consumer_manager):
        """Test error handling during consumption."""
        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_consumer.poll.side_effect = Exception("Connection error")

            messages = consumer_manager.consume(timeout_ms=1000)

            # Should return empty list on error
            assert messages == []

    def test_auto_commit_enabled(self):
        """Test consumer with auto commit enabled."""
        config = ConsumerConfig(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topics=["test-topic"],
            enable_auto_commit=True,
            auto_commit_interval_ms=5000,
        )

        with patch("src.streaming.kafka.consumer.KafkaConsumer") as mock_consumer_class:
            manager = KafkaConsumerManager(config)
            call_args = mock_consumer_class.call_args[1]
            assert call_args["enable_auto_commit"] is True

    def test_manual_commit_mode(self):
        """Test consumer with manual commit."""
        config = ConsumerConfig(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topics=["test-topic"],
            enable_auto_commit=False,
        )

        with patch("src.streaming.kafka.consumer.KafkaConsumer") as mock_consumer_class:
            manager = KafkaConsumerManager(config)
            call_args = mock_consumer_class.call_args[1]
            assert call_args["enable_auto_commit"] is False

    def test_get_partition_info(self, consumer_manager):
        """Test retrieving partition information."""
        topic = "test-topic"

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_consumer.partitions_for_topic.return_value = {0, 1, 2}

            partitions = consumer_manager.get_partitions(topic)

            assert len(partitions) == 3
            assert 0 in partitions

    def test_get_watermarks(self, consumer_manager):
        """Test retrieving high/low watermarks."""
        topic = "test-topic"
        partition = 0

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_consumer.beginning_offsets.return_value = {
                Mock(topic=topic, partition=partition): 0
            }
            mock_consumer.end_offsets.return_value = {
                Mock(topic=topic, partition=partition): 1000
            }

            watermarks = consumer_manager.get_watermarks(topic, partition)

            assert watermarks["low"] == 0
            assert watermarks["high"] == 1000

    def test_metrics(self, consumer_manager):
        """Test retrieving consumer metrics."""
        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_metrics = {
                "records-consumed-rate": 50.2,
                "records-lag-max": 100,
            }
            mock_consumer.metrics.return_value = mock_metrics

            metrics = consumer_manager.get_metrics()
            assert "records-consumed-rate" in metrics

    def test_batch_consumption(self, consumer_manager):
        """Test consuming messages in batches."""
        mock_messages = [
            Mock(
                topic="test-topic",
                partition=0,
                offset=i,
                key=f"key{i}".encode(),
                value=f'{{"id": {i}}}'.encode(),
                timestamp=1234567890000 + i,
            )
            for i in range(100)
        ]

        with patch.object(consumer_manager, "_consumer") as mock_consumer:
            mock_consumer.poll.return_value = {
                Mock(topic="test-topic", partition=0): mock_messages
            }

            messages = consumer_manager.consume(timeout_ms=5000, max_messages=50)

            # Should limit to max_messages
            assert len(messages) <= 50


class TestConsumerConfig:
    """Test suite for ConsumerConfig data class."""

    def test_default_config(self):
        """Test ConsumerConfig with default values."""
        config = ConsumerConfig(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topics=["test-topic"],
        )

        assert config.bootstrap_servers == "localhost:9092"
        assert config.group_id == "test-group"
        assert config.auto_offset_reset == "latest"
        assert config.enable_auto_commit is True

    def test_custom_config(self):
        """Test ConsumerConfig with custom values."""
        config = ConsumerConfig(
            bootstrap_servers="broker1:9092,broker2:9092",
            group_id="custom-group",
            topics=["topic1", "topic2"],
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            max_poll_records=100,
            session_timeout_ms=30000,
        )

        assert config.bootstrap_servers == "broker1:9092,broker2:9092"
        assert config.auto_offset_reset == "earliest"
        assert config.enable_auto_commit is False
        assert config.max_poll_records == 100

    def test_to_kafka_config(self):
        """Test converting ConsumerConfig to Kafka configuration dict."""
        config = ConsumerConfig(
            bootstrap_servers="localhost:9092",
            group_id="test-group",
            topics=["test-topic"],
            auto_offset_reset="earliest",
        )

        kafka_config = config.to_kafka_config()

        assert kafka_config["bootstrap_servers"] == "localhost:9092"
        assert kafka_config["group_id"] == "test-group"
        assert kafka_config["auto_offset_reset"] == "earliest"
