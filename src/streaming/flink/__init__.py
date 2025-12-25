"""
Apache Flink integration for stream processing.

Provides Flink jobs for Bronze → Silver → Gold transformations.
"""

from src.streaming.flink.jobs.bronze_to_silver import BronzeToSilverJob
from src.streaming.flink.jobs.silver_to_gold import SilverToGoldJob

__all__ = [
    "BronzeToSilverJob",
    "SilverToGoldJob",
]
