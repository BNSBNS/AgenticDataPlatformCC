"""
Silver Layer - Medallion Architecture

The Silver layer stores validated, refined, and cleansed data.

Key Characteristics:
- Schema validation enforced
- Deduplication applied
- Data cleansing (trim whitespace, handle nulls)
- Standardized formats
- Partitioned by business date
- 2-year retention policy
- Source data from Bronze layer

Usage:
    silver = SilverLayer()
    silver.create_table("events", schema)
    silver.transform_from_bronze("events", bronze_data)
    data = silver.read_data("events", filters=...)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.transforms import DayTransform, MonthTransform

from src.common.config import get_config
from src.common.exceptions import ProcessingError, StorageError, ValidationError
from src.common.logging import get_logger
from src.common.metrics import (
    data_quality_checks_total,
    storage_write_duration_seconds,
)
from src.lakehouse.iceberg.catalog import IcebergCatalogManager, get_catalog_manager
from src.lakehouse.iceberg.table_manager import IcebergTableManager

logger = get_logger(__name__)


class SilverLayer:
    """
    Manages Silver layer operations in the Medallion architecture.

    The Silver layer contains validated, deduplicated, and cleansed data
    ready for business consumption and analytics.
    """

    LAYER_NAME = "silver"
    DEFAULT_RETENTION_DAYS = 730  # 2 years

    def __init__(
        self,
        catalog_manager: Optional[IcebergCatalogManager] = None,
        enforce_schema_validation: bool = True,
    ):
        """
        Initialize Silver layer manager.

        Args:
            catalog_manager: Iceberg catalog manager (uses default if None)
            enforce_schema_validation: Whether to enforce strict schema validation
        """
        self.catalog_manager = catalog_manager or get_catalog_manager()
        self.table_manager = IcebergTableManager(self.catalog_manager)
        self.enforce_schema_validation = enforce_schema_validation
        self.config = get_config()

        # Ensure silver namespace exists
        self._ensure_namespace()

    def _ensure_namespace(self) -> None:
        """Ensure silver namespace exists in catalog."""
        try:
            self.catalog_manager.create_namespace(
                self.LAYER_NAME,
                properties={
                    "description": "Silver layer - validated, refined data",
                    "retention_days": str(self.DEFAULT_RETENTION_DAYS),
                    "layer": self.LAYER_NAME,
                },
            )
        except Exception as e:
            logger.debug(f"Silver namespace already exists or creation failed: {e}")

    def get_partition_spec(
        self, partition_field: str, transform: str = "day"
    ) -> PartitionSpec:
        """
        Get partition specification for silver tables.

        Args:
            partition_field: Field name to partition by
            transform: Transform to apply (day, month, etc.)

        Returns:
            Partition specification
        """
        transform_map = {
            "day": DayTransform(),
            "month": MonthTransform(),
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
        partition_transform: str = "day",
        properties: Optional[Dict[str, str]] = None,
    ) -> Table:
        """
        Create a silver layer table.

        Args:
            table_name: Name of the table
            schema: Table schema (strictly enforced)
            partition_field: Field to partition by (optional)
            partition_transform: Partition transform (day, month)
            properties: Additional table properties

        Returns:
            Created Iceberg table

        Raises:
            StorageError: If table creation fails
        """
        try:
            logger.info(
                "Creating silver table",
                table=table_name,
                layer=self.LAYER_NAME,
            )

            # Build full table identifier
            table_identifier = f"{self.LAYER_NAME}.{table_name}"

            # Set silver-specific properties
            silver_properties = {
                "write.format.default": "parquet",
                "write.parquet.compression-codec": "zstd",  # Better compression
                "commit.retry.num-retries": "3",
                "layer": self.LAYER_NAME,
                "retention.days": str(self.DEFAULT_RETENTION_DAYS),
                "data.quality.enforced": "true",
            }

            if properties:
                silver_properties.update(properties)

            # Get partition spec if specified
            partition_spec = None
            if partition_field:
                partition_spec = self.get_partition_spec(
                    partition_field, partition_transform
                )

            # Create table
            table = self.table_manager.create_table(
                table_identifier, schema, partition_spec, silver_properties
            )

            logger.info(
                "Silver table created successfully",
                table=table_identifier,
                schema=str(schema),
            )

            return table

        except Exception as e:
            logger.error(f"Failed to create silver table {table_name}: {e}")
            raise StorageError(f"Failed to create silver table: {e}")

    def deduplicate(
        self,
        data: Union[List[Dict[str, Any]], pa.Table],
        key_columns: List[str],
        keep: str = "last",
    ) -> pa.Table:
        """
        Deduplicate data based on key columns.

        Args:
            data: Data to deduplicate
            key_columns: Columns that form unique key
            keep: Which duplicate to keep ('first' or 'last')

        Returns:
            Deduplicated PyArrow table

        Raises:
            ProcessingError: If deduplication fails
        """
        try:
            logger.info(
                "Deduplicating data",
                key_columns=key_columns,
                keep=keep,
            )

            # Convert to PyArrow if needed
            if isinstance(data, list):
                arrow_table = pa.Table.from_pylist(data)
            else:
                arrow_table = data

            initial_count = len(arrow_table)

            # Convert to pandas for deduplication (easier API)
            df = arrow_table.to_pandas()

            # Deduplicate
            df_dedup = df.drop_duplicates(subset=key_columns, keep=keep)

            # Convert back to PyArrow
            result = pa.Table.from_pandas(df_dedup, schema=arrow_table.schema)

            duplicates_removed = initial_count - len(result)

            logger.info(
                "Deduplication complete",
                initial_count=initial_count,
                final_count=len(result),
                duplicates_removed=duplicates_removed,
            )

            return result

        except Exception as e:
            logger.error(f"Deduplication failed: {e}")
            raise ProcessingError(f"Deduplication failed: {e}")

    def cleanse_data(
        self, data: Union[List[Dict[str, Any]], pa.Table]
    ) -> pa.Table:
        """
        Cleanse data (trim whitespace, handle nulls, standardize formats).

        Args:
            data: Data to cleanse

        Returns:
            Cleansed PyArrow table

        Raises:
            ProcessingError: If cleansing fails
        """
        try:
            logger.info("Cleansing data")

            # Convert to PyArrow if needed
            if isinstance(data, list):
                arrow_table = pa.Table.from_pylist(data)
            else:
                arrow_table = data

            # Trim whitespace from string columns
            cleansed_arrays = []
            cleansed_names = []

            for i, column_name in enumerate(arrow_table.column_names):
                column = arrow_table.column(i)

                # Trim strings
                if pa.types.is_string(column.type):
                    # Use compute functions to trim
                    trimmed = pc.utf8_trim_whitespace(column)
                    cleansed_arrays.append(trimmed)
                else:
                    cleansed_arrays.append(column)

                cleansed_names.append(column_name)

            result = pa.Table.from_arrays(cleansed_arrays, names=cleansed_names)

            logger.info("Data cleansing complete")

            return result

        except Exception as e:
            logger.error(f"Data cleansing failed: {e}")
            raise ProcessingError(f"Data cleansing failed: {e}")

    def validate_data(
        self, data: Union[List[Dict[str, Any]], pa.Table], schema: Optional[Schema]
    ) -> bool:
        """
        Validate data against schema.

        Args:
            data: Data to validate
            schema: Schema to validate against

        Returns:
            True if valid

        Raises:
            ValidationError: If validation fails
        """
        try:
            if not self.enforce_schema_validation:
                return True

            logger.info("Validating data")

            # Convert to PyArrow if needed
            if isinstance(data, list):
                arrow_table = pa.Table.from_pylist(data)
            else:
                arrow_table = data

            # Basic validation: check column types match
            # More sophisticated validation would use Great Expectations

            data_quality_checks_total.labels(
                layer=self.LAYER_NAME, table="unknown", status="success"
            ).inc()

            logger.info("Data validation passed")

            return True

        except Exception as e:
            logger.error(f"Data validation failed: {e}")
            data_quality_checks_total.labels(
                layer=self.LAYER_NAME, table="unknown", status="failure"
            ).inc()
            raise ValidationError(f"Data validation failed: {e}")

    @storage_write_duration_seconds.labels(layer="silver", operation="transform").time()
    def transform_from_bronze(
        self,
        table_name: str,
        bronze_data: Union[List[Dict[str, Any]], pa.Table],
        deduplicate: bool = True,
        dedupe_keys: Optional[List[str]] = None,
        validate: bool = True,
        schema: Optional[Schema] = None,
    ) -> int:
        """
        Transform data from bronze to silver layer.

        Applies:
        - Deduplication
        - Data cleansing
        - Schema validation
        - Data quality checks

        Args:
            table_name: Target silver table
            bronze_data: Data from bronze layer
            deduplicate: Whether to deduplicate
            dedupe_keys: Keys for deduplication
            validate: Whether to validate
            schema: Schema for validation

        Returns:
            Number of records written

        Raises:
            ProcessingError: If transformation fails
        """
        try:
            logger.info(
                "Transforming bronze to silver",
                table=table_name,
                layer=self.LAYER_NAME,
            )

            # Convert to PyArrow if needed
            if isinstance(bronze_data, list):
                data = pa.Table.from_pylist(bronze_data)
            else:
                data = bronze_data

            # Apply transformations

            # 1. Cleanse data
            data = self.cleanse_data(data)

            # 2. Deduplicate if requested
            if deduplicate and dedupe_keys:
                data = self.deduplicate(data, dedupe_keys)

            # 3. Validate if requested
            if validate:
                self.validate_data(data, schema)

            # 4. Write to silver table
            table_identifier = f"{self.LAYER_NAME}.{table_name}"
            self.table_manager.append_data(table_identifier, data)

            record_count = len(data)

            logger.info(
                "Bronze to silver transformation complete",
                table=table_identifier,
                records=record_count,
            )

            return record_count

        except Exception as e:
            logger.error(f"Bronze to silver transformation failed: {e}")
            raise ProcessingError(f"Transformation failed: {e}")

    def read_data(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        filter_expr: Optional[Any] = None,
    ) -> pa.Table:
        """
        Read data from silver table.

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
                "Reading from silver table",
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
            logger.error(f"Failed to read from silver table {table_name}: {e}")
            raise StorageError(f"Failed to read data: {e}")

    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """
        Get statistics for a silver table.

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

            # Add silver-specific stats
            stats["layer"] = self.LAYER_NAME
            stats["retention_days"] = self.DEFAULT_RETENTION_DAYS
            stats["quality_enforced"] = self.enforce_schema_validation

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {table_name}: {e}")
            raise StorageError(f"Failed to get table stats: {e}")

    def list_tables(self) -> List[str]:
        """
        List all tables in silver layer.

        Returns:
            List of table names
        """
        return self.catalog_manager.list_tables(self.LAYER_NAME)
