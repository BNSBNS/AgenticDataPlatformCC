"""
Streaming ingestion using Kafka.

Provides event producers and schema definitions.
"""

from src.ingestion.streaming.event_producer import EventProducer
from src.ingestion.streaming.event_schemas import EventSchema

__all__ = [
    "EventProducer",
    "EventSchema",
]
