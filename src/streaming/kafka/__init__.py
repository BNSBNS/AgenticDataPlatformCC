"""
Kafka integration for streaming data.

Provides admin, producer, and consumer functionality.
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
