"""
Gold Layer - Medallion Architecture

The Gold layer stores curated, business-ready data optimized for analytics and ML.

Key Characteristics:
- Denormalized for query performance
- Business-level aggregations
- ML feature tables
- Partitioned by month for long-term storage
- 7-year retention policy
- Optimized for BI tools and dashboards

Usage:
    gold = GoldLayer()
    gold.create_table("daily_metrics", schema)
    gold.aggregate_from_silver("daily_metrics", silver_data, ...)
    gold.create_ml_features("user_features", data)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.transforms import MonthTransform, YearTransform

from src.common.config import get_config
from src.common.exceptions import ProcessingError, StorageError
from src.common.logging import get_logger
from src.common.metrics import storage_write_duration_seconds
from src.lakehouse.iceberg.catalog import IcebergCatalogManager, get_catalog_manager
from src.lakehouse.iceberg.table_manager import IcebergTableManager

logger = get_logger(__name__)


class GoldLayer:
    """
    Manages Gold layer operations in the Medallion architecture.

    The Gold layer contains curated, denormalized data optimized for
    business intelligence, reporting, and machine learning.
    """

    LAYER_NAME = "gold"
    DEFAULT_RETENTION_DAYS = 2555  # 7 years

    def __init__(
        self,
        catalog_manager: Optional[IcebergCatalogManager] = None,
        supports_denormalization: bool = True,
    ):
        """
        Initialize Gold layer manager.

        Args:
            catalog_manager: Iceberg catalog manager (uses default if None)
            supports_denormalization: Whether to support denormalized views
        """
        self.catalog_manager = catalog_manager or get_catalog_manager()
        self.table_manager = IcebergTableManager(self.catalog_manager)
        self.supports_denormalization = supports_denormalization
        self.config = get_config()

        # Ensure gold namespace exists
        self._ensure_namespace()

    def _ensure_namespace(self) -> None:
        """Ensure gold namespace exists in catalog."""
        try:
            self.catalog_manager.create_namespace(
                self.LAYER_NAME,
                properties={
                    "description": "Gold layer - curated, business-ready data",
                    "retention_days": str(self.DEFAULT_RETENTION_DAYS),
                    "layer": self.LAYER_NAME,
                },
            )
        except Exception as e:
            logger.debug(f"Gold namespace already exists or creation failed: {e}")

    def get_partition_spec(
        self, partition_field: str, transform: str = "month"
    ) -> PartitionSpec:
        """
        Get partition specification for gold tables.

        Gold tables typically use month or year partitioning for
        long-term storage and efficient querying.

        Args:
            partition_field: Field name to partition by
            transform: Transform to apply (month, year)

        Returns:
            Partition specification
        """
        transform_map = {
            "month": MonthTransform(),
            "year": YearTransform(),
        }

        if transform not in transform_map:
            raise ValueError(f"Unsupported transform: {transform}")

        partition = PartitionField(
            source_id=1,  # Will be updated based on schema
            field_id=1000,
            transform=transform_map[transform],
            name=f"{partition_field}_{transform}",
        )

        return PartitionSpec(partition)

    def create_table(
        self,
        table_name: str,
        schema: Schema,
        partition_field: Optional[str] = None,
        partition_transform: str = "month",
        properties: Optional[Dict[str, str]] = None,
    ) -> Table:
        """
        Create a gold layer table.

        Args:
            table_name: Name of the table
            schema: Table schema
            partition_field: Field to partition by (optional)
            partition_transform: Partition transform (month, year)
            properties: Additional table properties

        Returns:
            Created Iceberg table

        Raises:
            StorageError: If table creation fails
        """
        try:
            logger.info(
                "Creating gold table",
                table=table_name,
                layer=self.LAYER_NAME,
            )

            # Build full table identifier
            table_identifier = f"{self.LAYER_NAME}.{table_name}"

            # Set gold-specific properties
            gold_properties = {
                "write.format.default": "parquet",
                "write.parquet.compression-codec": "zstd",  # Best compression
                "commit.retry.num-retries": "3",
                "layer": self.LAYER_NAME,
                "retention.days": str(self.DEFAULT_RETENTION_DAYS),
                "optimization": "analytics",
                "materialized": "true",
            }

            if properties:
                gold_properties.update(properties)

            # Get partition spec if specified
            partition_spec = None
            if partition_field:
                partition_spec = self.get_partition_spec(
                    partition_field, partition_transform
                )

            # Create table
            table = self.table_manager.create_table(
                table_identifier, schema, partition_spec, gold_properties
            )

            logger.info(
                "Gold table created successfully",
                table=table_identifier,
                schema=str(schema),
            )

            return table

        except Exception as e:
            logger.error(f"Failed to create gold table {table_name}: {e}")
            raise StorageError(f"Failed to create gold table: {e}")

    @storage_write_duration_seconds.labels(layer="gold", operation="aggregate").time()
    def aggregate_from_silver(
        self,
        table_name: str,
        silver_data: Union[List[Dict[str, Any]], pa.Table],
        group_by: List[str],
        aggregations: Dict[str, str],
    ) -> int:
        """
        Aggregate data from silver to gold layer.

        Args:
            table_name: Target gold table
            silver_data: Data from silver layer
            group_by: Columns to group by
            aggregations: Aggregation functions (column: function)
                Example: {"revenue": "sum", "count": "count"}

        Returns:
            Number of records written

        Raises:
            ProcessingError: If aggregation fails
        """
        try:
            logger.info(
                "Aggregating silver to gold",
                table=table_name,
                group_by=group_by,
                aggregations=aggregations,
            )

            # Convert to PyArrow if needed
            if isinstance(silver_data, list):
                data = pa.Table.from_pylist(silver_data)
            else:
                data = silver_data

            # Convert to pandas for easier aggregation
            df = data.to_pandas()

            # Build aggregation dictionary
            agg_dict = {}
            for column, func in aggregations.items():
                if func == "sum":
                    agg_dict[column] = "sum"
                elif func == "count":
                    agg_dict[column] = "count"
                elif func == "avg" or func == "mean":
                    agg_dict[column] = "mean"
                elif func == "min":
                    agg_dict[column] = "min"
                elif func == "max":
                    agg_dict[column] = "max"
                else:
                    logger.warning(f"Unknown aggregation function: {func}")

            # Perform aggregation
            aggregated = df.groupby(group_by).agg(agg_dict).reset_index()

            # Convert back to PyArrow
            result = pa.Table.from_pandas(aggregated)

            # Write to gold table
            table_identifier = f"{self.LAYER_NAME}.{table_name}"
            self.table_manager.append_data(table_identifier, result)

            record_count = len(result)

            logger.info(
                "Silver to gold aggregation complete",
                table=table_identifier,
                records=record_count,
            )

            return record_count

        except Exception as e:
            logger.error(f"Silver to gold aggregation failed: {e}")
            raise ProcessingError(f"Aggregation failed: {e}")

    def compute_metrics(
        self,
        data: Union[List[Dict[str, Any]], pa.Table],
        metrics: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Compute business-level metrics from data.

        Args:
            data: Input data
            metrics: Metric definitions (name: expression)
                Example: {"total_revenue": "sum(revenue)", "profit": "sum(revenue) - sum(cost)"}

        Returns:
            Dictionary of computed metrics

        Raises:
            ProcessingError: If computation fails
        """
        try:
            logger.info("Computing business metrics", metrics=list(metrics.keys()))

            # Convert to PyArrow if needed
            if isinstance(data, list):
                arrow_table = pa.Table.from_pylist(data)
            else:
                arrow_table = data

            # Convert to pandas for easier computation
            df = arrow_table.to_pandas()

            results = {}

            # Compute each metric
            # This is a simplified implementation
            # Production would use a SQL-like expression parser
            for metric_name, expression in metrics.items():
                # Simple parsing for basic aggregations
                if "sum(" in expression:
                    # Extract column name
                    col = expression.split("(")[1].split(")")[0]
                    results[metric_name] = df[col].sum()
                elif "count(" in expression:
                    col = expression.split("(")[1].split(")")[0]
                    results[metric_name] = df[col].count()
                elif "avg(" in expression or "mean(" in expression:
                    col = expression.split("(")[1].split(")")[0]
                    results[metric_name] = df[col].mean()
                else:
                    # For complex expressions, would need eval (use carefully in production)
                    logger.warning(f"Complex metric expression not supported: {expression}")

            logger.info("Metrics computed successfully", metrics=results)

            return results

        except Exception as e:
            logger.error(f"Metric computation failed: {e}")
            raise ProcessingError(f"Metric computation failed: {e}")

    def create_ml_features(
        self,
        table_name: str,
        data: Union[List[Dict[str, Any]], pa.Table],
        feature_columns: List[str],
        target_column: Optional[str] = None,
    ) -> int:
        """
        Create ML feature table from data.

        Args:
            table_name: Target feature table name
            data: Input data
            feature_columns: Columns to use as features
            target_column: Target variable column (optional)

        Returns:
            Number of records written

        Raises:
            ProcessingError: If feature creation fails
        """
        try:
            logger.info(
                "Creating ML features",
                table=table_name,
                features=feature_columns,
                target=target_column,
            )

            # Convert to PyArrow if needed
            if isinstance(data, list):
                arrow_table = pa.Table.from_pylist(data)
            else:
                arrow_table = data

            # Select feature columns (and target if specified)
            columns_to_select = feature_columns.copy()
            if target_column:
                columns_to_select.append(target_column)

            # Select only specified columns
            feature_table = arrow_table.select(columns_to_select)

            # Write to gold table
            table_identifier = f"{self.LAYER_NAME}.{table_name}"
            self.table_manager.append_data(table_identifier, feature_table)

            record_count = len(feature_table)

            logger.info(
                "ML features created successfully",
                table=table_identifier,
                records=record_count,
            )

            return record_count

        except Exception as e:
            logger.error(f"ML feature creation failed: {e}")
            raise ProcessingError(f"ML feature creation failed: {e}")

    def read_data(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        filter_expr: Optional[Any] = None,
    ) -> pa.Table:
        """
        Read data from gold table.

        Args:
            table_name: Table name to read from
            columns: Columns to select (None = all)
            limit: Maximum number of rows
            filter_expr: Iceberg filter expression

        Returns:
            PyArrow table with data

        Raises:
            StorageError: If read fails
        """
        try:
            table_identifier = f"{self.LAYER_NAME}.{table_name}"

            logger.info(
                "Reading from gold table",
                table=table_identifier,
                columns=columns,
                limit=limit,
            )

            data = self.table_manager.read_table(
                table_identifier, columns, filter_expr, limit
            )

            logger.info(
                "Data read successfully",
                table=table_identifier,
                rows=len(data),
            )

            return data

        except Exception as e:
            logger.error(f"Failed to read from gold table {table_name}: {e}")
            raise StorageError(f"Failed to read data: {e}")

    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """
        Get statistics for a gold table.

        Args:
            table_name: Table name

        Returns:
            Dictionary with table statistics

        Raises:
            StorageError: If operation fails
        """
        try:
            table_identifier = f"{self.LAYER_NAME}.{table_name}"
            table = self.catalog_manager.load_table(table_identifier)

            stats = self.table_manager.get_table_metadata(table)

            # Add gold-specific stats
            stats["layer"] = self.LAYER_NAME
            stats["retention_days"] = self.DEFAULT_RETENTION_DAYS
            stats["optimized_for"] = "analytics"

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {table_name}: {e}")
            raise StorageError(f"Failed to get table stats: {e}")

    def list_tables(self) -> List[str]:
        """
        List all tables in gold layer.

        Returns:
            List of table names
        """
        return self.catalog_manager.list_tables(self.LAYER_NAME)
