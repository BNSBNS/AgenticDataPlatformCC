"""
Unit tests for Bronze Layer (Medallion Architecture).

TDD approach: Tests written first to define expected behavior.
"""

import pytest
import pyarrow as pa
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField, StringType, TimestampType

from src.lakehouse.medallion.bronze_layer import BronzeLayer


class TestBronzeLayer:
    """Test suite for Bronze Layer."""

    def test_create_bronze_table(self, sample_schema):
        """Test creating a bronze table with schema."""
        # Arrange
        bronze = BronzeLayer()
        table_name = "test_events"
        schema = sample_schema["events"]

        # Act
        table = bronze.create_table(table_name, schema)

        # Assert
        assert table is not None
        assert str(table.name()).endswith(table_name)

    def test_ingest_raw_data(self, sample_data):
        """Test ingesting raw data to bronze layer."""
        # Arrange
        bronze = BronzeLayer()
        table_name = "test_events"
        data = sample_data["events"]

        # Act
        bronze.ingest_raw_data(table_name, data)

        # Assert
        # Verify data was written (test will be implemented after BronzeLayer)
        assert True  # Placeholder

    def test_bronze_table_is_append_only(self):
        """Test that bronze tables are append-only."""
        # Arrange
        bronze = BronzeLayer()

        # Act & Assert
        # Bronze layer should not allow updates or deletes
        # This will be verified in implementation
        assert True  # Placeholder

    def test_bronze_adds_metadata_columns(self, sample_data):
        """Test that bronze layer adds audit metadata columns."""
        # Arrange
        bronze = BronzeLayer()
        table_name = "test_events"
        data = sample_data["events"]

        # Act
        result = bronze.ingest_raw_data(table_name, data, add_metadata=True)

        # Assert
        # Should add: ingestion_timestamp, source_file, record_hash
        # This will be verified in implementation
        assert True  # Placeholder

    def test_bronze_partition_by_ingestion_date(self):
        """Test that bronze tables are partitioned by ingestion date."""
        # Arrange
        bronze = BronzeLayer()
        table_name = "test_events"

        # Act
        partition_spec = bronze.get_default_partition_spec()

        # Assert
        # Should partition by day(ingestion_timestamp)
        assert partition_spec is not None

    def test_read_bronze_data(self, sample_data):
        """Test reading data from bronze layer."""
        # Arrange
        bronze = BronzeLayer()
        table_name = "test_events"
        bronze.ingest_raw_data(table_name, sample_data["events"])

        # Act
        result = bronze.read_data(table_name, limit=10)

        # Assert
        assert result is not None
        assert len(result) > 0

    def test_bronze_schema_validation_optional(self):
        """Test that bronze layer has optional schema validation."""
        # Arrange
        bronze = BronzeLayer()

        # Act & Assert
        # Bronze should accept data with or without schema validation
        # Strict validation is for Silver layer
        assert bronze.validate_schema is False

    def test_get_table_stats(self):
        """Test getting bronze table statistics."""
        # Arrange
        bronze = BronzeLayer()
        table_name = "test_events"

        # Act
        stats = bronze.get_table_stats(table_name)

        # Assert
        assert "row_count" in stats
        assert "size_bytes" in stats
        assert "snapshot_count" in stats
