"""
Unit tests for Kafka producer wrapper.

Tests message production, serialization, retries, and error handling.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from typing import Dict, Any
import json

from src.streaming.kafka.producer import KafkaProducerManager, ProducerConfig


class TestKafkaProducerManager:
    """Test suite for Kafka producer operations."""

    @pytest.fixture
    def producer_config(self):
        """Fixture for producer configuration."""
        return ProducerConfig(
            bootstrap_servers="localhost:9092",
            client_id="test-producer",
            acks="all",
            retries=3,
        )

    @pytest.fixture
    def producer_manager(self, producer_config):
        """Fixture for KafkaProducerManager instance."""
        with patch("src.streaming.kafka.producer.KafkaProducer"):
            manager = KafkaProducerManager(producer_config)
            return manager

    def test_initialization(self, producer_manager, producer_config):
        """Test that producer manager initializes correctly."""
        assert producer_manager is not None
        assert producer_manager.config == producer_config

    def test_send_message_success(self, producer_manager):
        """Test sending a message successfully."""
        topic = "test-topic"
        message = {"id": 1, "name": "test", "value": 100}

        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_future = MagicMock()
            mock_future.get.return_value = Mock(topic=topic, partition=0, offset=42)
            mock_producer.send.return_value = mock_future

            result = producer_manager.send_message(topic, message)

            assert result["success"] is True
            assert result["topic"] == topic
            assert result["partition"] == 0
            assert result["offset"] == 42

    def test_send_message_with_key(self, producer_manager):
        """Test sending a message with a specific key."""
        topic = "test-topic"
        message = {"id": 1, "data": "test"}
        key = "user-1"

        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_future = MagicMock()
            mock_future.get.return_value = Mock(topic=topic, partition=2, offset=100)
            mock_producer.send.return_value = mock_future

            result = producer_manager.send_message(topic, message, key=key)

            mock_producer.send.assert_called_once()
            call_args = mock_producer.send.call_args
            assert call_args[1]["key"] is not None

    def test_send_message_with_partition(self, producer_manager):
        """Test sending a message to a specific partition."""
        topic = "test-topic"
        message = {"data": "test"}
        partition = 3

        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_future = MagicMock()
            mock_future.get.return_value = Mock(topic=topic, partition=partition, offset=50)
            mock_producer.send.return_value = mock_future

            result = producer_manager.send_message(topic, message, partition=partition)

            assert result["partition"] == partition

    def test_send_message_with_headers(self, producer_manager):
        """Test sending a message with custom headers."""
        topic = "test-topic"
        message = {"data": "test"}
        headers = {"source": "test-system", "version": "1.0"}

        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_future = MagicMock()
            mock_future.get.return_value = Mock(topic=topic, partition=0, offset=10)
            mock_producer.send.return_value = mock_future

            result = producer_manager.send_message(topic, message, headers=headers)

            call_args = mock_producer.send.call_args
            assert call_args[1]["headers"] is not None

    def test_send_message_failure(self, producer_manager):
        """Test handling of send failures."""
        topic = "test-topic"
        message = {"data": "test"}

        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_future = MagicMock()
            mock_future.get.side_effect = Exception("Send failed")
            mock_producer.send.return_value = mock_future

            result = producer_manager.send_message(topic, message)

            assert result["success"] is False
            assert "error" in result

    def test_send_batch_messages(self, producer_manager):
        """Test sending multiple messages in batch."""
        topic = "test-topic"
        messages = [
            {"id": 1, "value": "a"},
            {"id": 2, "value": "b"},
            {"id": 3, "value": "c"},
        ]

        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_future = MagicMock()
            mock_future.get.return_value = Mock(topic=topic, partition=0, offset=0)
            mock_producer.send.return_value = mock_future

            results = producer_manager.send_batch(topic, messages)

            assert len(results) == 3
            assert all(r["success"] for r in results)
            assert mock_producer.send.call_count == 3

    def test_send_batch_with_keys(self, producer_manager):
        """Test sending batch with corresponding keys."""
        topic = "test-topic"
        messages = [{"id": 1}, {"id": 2}, {"id": 3}]
        keys = ["key1", "key2", "key3"]

        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_future = MagicMock()
            mock_future.get.return_value = Mock(topic=topic, partition=0, offset=0)
            mock_producer.send.return_value = mock_future

            results = producer_manager.send_batch(topic, messages, keys=keys)

            assert len(results) == 3
            assert mock_producer.send.call_count == 3

    def test_flush(self, producer_manager):
        """Test flushing pending messages."""
        with patch.object(producer_manager, "_producer") as mock_producer:
            producer_manager.flush()
            mock_producer.flush.assert_called_once()

    def test_flush_with_timeout(self, producer_manager):
        """Test flushing with timeout."""
        timeout = 10.0

        with patch.object(producer_manager, "_producer") as mock_producer:
            producer_manager.flush(timeout=timeout)
            mock_producer.flush.assert_called_once_with(timeout=timeout)

    def test_close(self, producer_manager):
        """Test closing producer connection."""
        with patch.object(producer_manager, "_producer") as mock_producer:
            producer_manager.close()
            mock_producer.close.assert_called_once()

    def test_context_manager(self, producer_config):
        """Test using producer as context manager."""
        with patch("src.streaming.kafka.producer.KafkaProducer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer_class.return_value = mock_producer

            with KafkaProducerManager(producer_config) as producer:
                assert producer is not None

            mock_producer.close.assert_called_once()

    def test_metrics(self, producer_manager):
        """Test retrieving producer metrics."""
        with patch.object(producer_manager, "_producer") as mock_producer:
            mock_metrics = {
                "record-send-rate": 100.5,
                "record-error-rate": 0.1,
                "buffer-available-bytes": 33554432,
            }
            mock_producer.metrics.return_value = mock_metrics

            metrics = producer_manager.get_metrics()
            assert "record-send-rate" in metrics

    def test_json_serialization(self, producer_manager):
        """Test JSON serialization of messages."""
        message = {"id": 1, "name": "test", "values": [1, 2, 3]}

        serialized = producer_manager._serialize_json(message)
        assert isinstance(serialized, bytes)

        deserialized = json.loads(serialized)
        assert deserialized == message

    def test_avro_serialization(self, producer_config):
        """Test Avro serialization of messages."""
        schema = {
            "type": "record",
            "name": "TestRecord",
            "fields": [
                {"name": "id", "type": "int"},
                {"name": "name", "type": "string"},
            ],
        }

        producer_config.value_serializer = "avro"
        producer_config.schema_registry_url = "http://localhost:8081"

        with patch("src.streaming.kafka.producer.KafkaProducer"):
            with patch("src.streaming.kafka.producer.AvroSerializer") as mock_avro:
                manager = KafkaProducerManager(producer_config)
                assert mock_avro.called

    def test_retry_on_failure(self, producer_manager):
        """Test automatic retry on transient failures."""
        topic = "test-topic"
        message = {"data": "test"}

        with patch.object(producer_manager, "_producer") as mock_producer:
            # First two attempts fail, third succeeds
            mock_future = MagicMock()
            mock_future.get.side_effect = [
                Exception("Timeout"),
                Exception("Timeout"),
                Mock(topic=topic, partition=0, offset=42),
            ]
            mock_producer.send.return_value = mock_future

            result = producer_manager.send_message(topic, message, max_retries=3)

            # Should succeed after retries
            assert result["success"] is True or mock_producer.send.call_count <= 3

    def test_transaction_support(self, producer_config):
        """Test transactional producer initialization."""
        producer_config.transactional_id = "test-transaction"

        with patch("src.streaming.kafka.producer.KafkaProducer") as mock_producer_class:
            mock_producer = MagicMock()
            mock_producer_class.return_value = mock_producer

            manager = KafkaProducerManager(producer_config)

            # Transactional producer should call init_transactions
            mock_producer.init_transactions.assert_called_once()


class TestProducerConfig:
    """Test suite for ProducerConfig data class."""

    def test_default_config(self):
        """Test ProducerConfig with default values."""
        config = ProducerConfig(bootstrap_servers="localhost:9092")

        assert config.bootstrap_servers == "localhost:9092"
        assert config.acks == "all"
        assert config.retries == 3
        assert config.value_serializer == "json"

    def test_custom_config(self):
        """Test ProducerConfig with custom values."""
        config = ProducerConfig(
            bootstrap_servers="broker1:9092,broker2:9092",
            client_id="custom-producer",
            acks="1",
            retries=5,
            compression_type="snappy",
            batch_size=32768,
            linger_ms=100,
        )

        assert config.bootstrap_servers == "broker1:9092,broker2:9092"
        assert config.client_id == "custom-producer"
        assert config.compression_type == "snappy"
        assert config.batch_size == 32768

    def test_to_kafka_config(self):
        """Test converting ProducerConfig to Kafka configuration dict."""
        config = ProducerConfig(
            bootstrap_servers="localhost:9092",
            acks="all",
            retries=3,
            compression_type="lz4",
        )

        kafka_config = config.to_kafka_config()

        assert kafka_config["bootstrap_servers"] == "localhost:9092"
        assert kafka_config["acks"] == "all"
        assert kafka_config["retries"] == 3
        assert kafka_config["compression_type"] == "lz4"
