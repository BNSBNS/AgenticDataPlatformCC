"""
Data ingestion layer for the platform.

Provides batch and streaming ingestion capabilities.
"""

from src.ingestion.streaming import EventProducer, EventSchema

__all__ = [
    "EventProducer",
    "EventSchema",
]
