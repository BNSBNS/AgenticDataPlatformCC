"""
Unit tests for Gold Layer (Medallion Architecture).

TDD approach: Tests define expected behavior for curated, business-ready data.
"""

import pytest
import pyarrow as pa

from src.lakehouse.medallion.gold_layer import GoldLayer


class TestGoldLayer:
    """Test suite for Gold Layer."""

    def test_create_gold_table(self, sample_schema):
        """Test creating a gold table for business metrics."""
        # Arrange
        gold = GoldLayer()
        table_name = "daily_metrics"
        schema = sample_schema["events"]

        # Act
        table = gold.create_table(table_name, schema)

        # Assert
        assert table is not None
        assert str(table.name()).endswith(table_name)

    def test_aggregate_from_silver(self, sample_data):
        """Test aggregating data from silver to gold."""
        # Arrange
        gold = GoldLayer()
        silver_data = sample_data["events"]

        # Act
        aggregated = gold.aggregate_from_silver(
            "daily_metrics",
            silver_data,
            group_by=["name"],
            aggregations={"value": "sum"},
        )

        # Assert
        assert aggregated is not None

    def test_gold_partition_by_month(self):
        """Test that gold tables are partitioned by month for long-term storage."""
        # Arrange
        gold = GoldLayer()

        # Act
        partition_spec = gold.get_partition_spec(
            partition_field="metric_date", transform="month"
        )

        # Assert
        assert partition_spec is not None

    def test_gold_creates_denormalized_views(self):
        """Test that gold layer creates denormalized, BI-ready views."""
        # Arrange
        gold = GoldLayer()

        # Act & Assert
        # Gold should support wide, denormalized tables
        assert gold.supports_denormalization is True

    def test_gold_computes_business_metrics(self):
        """Test computing business-level metrics."""
        # Arrange
        gold = GoldLayer()
        silver_data = [
            {"date": "2024-01-01", "revenue": 1000, "cost": 600},
            {"date": "2024-01-02", "revenue": 1500, "cost": 700},
        ]

        # Act
        metrics = gold.compute_metrics(
            silver_data,
            metrics={
                "total_revenue": "sum(revenue)",
                "total_cost": "sum(cost)",
                "profit": "sum(revenue) - sum(cost)",
            },
        )

        # Assert
        assert "total_revenue" in metrics
        assert "total_cost" in metrics
        assert "profit" in metrics

    def test_gold_creates_ml_features(self):
        """Test creating ML feature tables."""
        # Arrange
        gold = GoldLayer()
        silver_data = sample_data["users"]

        # Act
        features = gold.create_ml_features(
            "user_features",
            silver_data,
            feature_columns=["user_id", "username"],
        )

        # Assert
        assert features is not None

    def test_read_gold_data(self):
        """Test reading data from gold layer."""
        # Arrange
        gold = GoldLayer()
        table_name = "daily_metrics"

        # Act
        result = gold.read_data(table_name, limit=10)

        # Assert
        assert result is not None
