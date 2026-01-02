"""
Pytest configuration and shared fixtures.

This module provides common fixtures and configuration for all tests.
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Generator

import pytest
from _pytest.monkeypatch import MonkeyPatch

# Set test environment
os.environ["ENVIRONMENT"] = "development"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["DEBUG"] = "true"


@pytest.fixture(scope="session")
def test_config() -> Dict:
    """
    Provide test configuration.

    Returns:
        Dictionary with test configuration values
    """
    return {
        "storage_type": "minio",
        "storage_endpoint": "http://localhost:9000",
        "storage_access_key": "minioadmin",
        "storage_secret_key": "minioadmin",
        "kafka_bootstrap_servers": "localhost:9092",
        "postgres_host": "localhost",
        "postgres_port": 5432,
    }


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for test files.

    Yields:
        Path to temporary directory
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_env_vars(monkeypatch: MonkeyPatch) -> Generator[MonkeyPatch, None, None]:
    """
    Provide a monkeypatch instance for mocking environment variables.

    Args:
        monkeypatch: Pytest monkeypatch fixture

    Yields:
        MonkeyPatch instance
    """
    yield monkeypatch


@pytest.fixture
def sample_data() -> Dict:
    """
    Provide sample data for testing.

    Returns:
        Dictionary with sample data
    """
    return {
        "events": [
            {"id": 1, "name": "event1", "timestamp": 1735100000, "value": 100.0},
            {"id": 2, "name": "event2", "timestamp": 1735100001, "value": 200.0},
            {"id": 3, "name": "event3", "timestamp": 1735100002, "value": 300.0},
        ],
        "users": [
            {"user_id": 1, "username": "alice", "email": "alice@example.com"},
            {"user_id": 2, "username": "bob", "email": "bob@example.com"},
            {"user_id": 3, "username": "charlie", "email": "charlie@example.com"},
        ],
    }


@pytest.fixture
def sample_schema() -> Dict:
    """
    Provide sample schema definitions.

    Returns:
        Dictionary with sample schemas
    """
    from pyiceberg.schema import Schema
    from pyiceberg.types import (
        DoubleType,
        LongType,
        NestedField,
        StringType,
        TimestampType,
    )

    return {
        "events": Schema(
            NestedField(1, "id", LongType(), required=True),
            NestedField(2, "name", StringType(), required=True),
            NestedField(3, "timestamp", LongType(), required=True),
            NestedField(4, "value", DoubleType(), required=False),
        ),
        "users": Schema(
            NestedField(1, "user_id", LongType(), required=True),
            NestedField(2, "username", StringType(), required=True),
            NestedField(3, "email", StringType(), required=True),
            NestedField(4, "created_at", TimestampType(), required=False),
        ),
    }


# Markers for different test types
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "requires_docker: Tests that require Docker services")
    config.addinivalue_line("markers", "requires_kafka: Tests that require Kafka")
    config.addinivalue_line("markers", "requires_postgres: Tests that require PostgreSQL")
    config.addinivalue_line("markers", "requires_minio: Tests that require MinIO")
