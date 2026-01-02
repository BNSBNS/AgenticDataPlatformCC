"""
Query layer for data access.

Provides Trino/Spark integration for querying the lakehouse.
"""

from src.query.trino.executor import TrinoQueryExecutor
from src.query.spark.session import SparkSessionManager

__all__ = [
    "TrinoQueryExecutor",
    "SparkSessionManager",
]
