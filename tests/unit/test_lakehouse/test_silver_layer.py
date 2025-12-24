"""
Unit tests for Silver Layer (Medallion Architecture).

TDD approach: Tests define expected behavior for validated, refined data.
"""

import pytest
import pyarrow as pa

from src.lakehouse.medallion.silver_layer import SilverLayer


class TestSilverLayer:
    """Test suite for Silver Layer."""

    def test_create_silver_table(self, sample_schema):
        """Test creating a silver table with strict schema."""
        # Arrange
        silver = SilverLayer()
        table_name = "test_events"
        schema = sample_schema["events"]

        # Act
        table = silver.create_table(table_name, schema)

        # Assert
        assert table is not None
        assert str(table.name()).endswith(table_name)

    def test_transform_from_bronze(self, sample_data):
        """Test transforming data from bronze to silver."""
        # Arrange
        silver = SilverLayer()
        bronze_data = sample_data["events"]

        # Act
        transformed = silver.transform_from_bronze(
            "test_events", bronze_data, deduplicate=True, validate=True
        )

        # Assert
        assert transformed is not None

    def test_silver_enforces_schema_validation(self):
        """Test that silver layer enforces schema validation."""
        # Arrange
        silver = SilverLayer()

        # Act & Assert
        assert silver.enforce_schema_validation is True

    def test_silver_deduplicates_data(self, sample_data):
        """Test that silver layer deduplicates records."""
        # Arrange
        silver = SilverLayer()

        # Duplicate data
        duplicated_data = sample_data["events"] + sample_data["events"]

        # Act
        deduplicated = silver.deduplicate(duplicated_data, key_columns=["id"])

        # Assert
        assert len(deduplicated) == len(sample_data["events"])

    def test_silver_validates_data_types(self):
        """Test that silver layer validates data types."""
        # Arrange
        silver = SilverLayer()
        invalid_data = [{"id": "not_a_number", "name": "test"}]  # Invalid type

        # Act & Assert
        with pytest.raises(Exception):  # Should raise validation error
            silver.validate_data(invalid_data, schema=None)

    def test_silver_cleanses_data(self):
        """Test data cleansing functions."""
        # Arrange
        silver = SilverLayer()
        dirty_data = [
            {"id": 1, "name": "  test  ", "value": None},  # Whitespace, null
        ]

        # Act
        clean = silver.cleanse_data(dirty_data)

        # Assert
        assert clean[0]["name"] == "test"  # Trimmed whitespace

    def test_silver_partition_by_business_date(self):
        """Test that silver tables can partition by business date."""
        # Arrange
        silver = SilverLayer()
        table_name = "test_events"

        # Act
        partition_spec = silver.get_partition_spec(
            partition_field="event_date", transform="day"
        )

        # Assert
        assert partition_spec is not None

    def test_read_silver_data(self):
        """Test reading data from silver layer."""
        # Arrange
        silver = SilverLayer()
        table_name = "test_events"

        # Act
        result = silver.read_data(table_name, limit=10)

        # Assert
        assert result is not None
