"""
Streaming infrastructure for the data platform.

Provides Kafka and Flink integration for real-time data processing.
"""

from src.streaming.kafka.admin import KafkaAdminManager, TopicConfig
from src.streaming.kafka.producer import KafkaProducerManager, ProducerConfig
from src.streaming.kafka.consumer import KafkaConsumerManager, ConsumerConfig

__all__ = [
    "KafkaAdminManager",
    "TopicConfig",
    "KafkaProducerManager",
    "ProducerConfig",
    "KafkaConsumerManager",
    "ConsumerConfig",
]
