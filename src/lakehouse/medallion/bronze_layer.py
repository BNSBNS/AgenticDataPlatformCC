"""
Bronze Layer - Medallion Architecture

The Bronze layer stores raw, immutable data as ingested from sources.

Key Characteristics:
- Append-only (no updates or deletes)
- Raw data format (minimal transformation)
- Full audit trail with metadata
- Partitioned by ingestion date
- 90-day retention policy
- Schema validation is optional

Usage:
    bronze = BronzeLayer()
    bronze.create_table("events", schema)
    bronze.ingest_raw_data("events", data)
    data = bronze.read_data("events", limit=100)
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.transforms import DayTransform
from pyiceberg.types import LongType, NestedField, StringType, TimestampType

from src.common.config import get_config
from src.common.exceptions import IngestionError, StorageError
from src.common.logging import get_logger
from src.common.metrics import (
    ingestion_bytes_total,
    ingestion_duration_seconds,
    ingestion_records_total,
)
from src.lakehouse.iceberg.catalog import IcebergCatalogManager, get_catalog_manager
from src.lakehouse.iceberg.table_manager import IcebergTableManager

logger = get_logger(__name__)


class BronzeLayer:
    """
    Manages Bronze layer operations in the Medallion architecture.

    The Bronze layer is the landing zone for raw data with minimal
    transformation. It maintains data lineage and provides a complete
    audit trail.
    """

    LAYER_NAME = "bronze"
    DEFAULT_RETENTION_DAYS = 90

    def __init__(
        self,
        catalog_manager: Optional[IcebergCatalogManager] = None,
        validate_schema: bool = False,
    ):
        """
        Initialize Bronze layer manager.

        Args:
            catalog_manager: Iceberg catalog manager (uses default if None)
            validate_schema: Whether to enforce schema validation (default: False)
        """
        self.catalog_manager = catalog_manager or get_catalog_manager()
        self.table_manager = IcebergTableManager(self.catalog_manager)
        self.validate_schema = validate_schema
        self.config = get_config()

        # Ensure bronze namespace exists
        self._ensure_namespace()

    def _ensure_namespace(self) -> None:
        """Ensure bronze namespace exists in catalog."""
        try:
            self.catalog_manager.create_namespace(
                self.LAYER_NAME,
                properties={
                    "description": "Bronze layer - raw, immutable data",
                    "retention_days": str(self.DEFAULT_RETENTION_DAYS),
                    "layer": self.LAYER_NAME,
                },
            )
        except Exception as e:
            logger.debug(f"Bronze namespace already exists or creation failed: {e}")

    def _add_metadata_fields(self, schema: Schema) -> Schema:
        """
        Add metadata fields to schema for audit trail.

        Args:
            schema: Original schema

        Returns:
            Schema with added metadata fields
        """
        # Get max field ID from existing schema
        max_id = max([field.field_id for field in schema.fields])

        # Add metadata fields
        metadata_fields = [
            NestedField(
                max_id + 1,
                "ingestion_timestamp",
                TimestampType(),
                required=True,
                doc="Timestamp when data was ingested",
            ),
            NestedField(
                max_id + 2,
                "source_system",
                StringType(),
                required=False,
                doc="Source system name",
            ),
            NestedField(
                max_id + 3,
                "source_file",
                StringType(),
                required=False,
                doc="Source file or identifier",
            ),
            NestedField(
                max_id + 4,
                "record_hash",
                StringType(),
                required=False,
                doc="Hash of record for deduplication",
            ),
        ]

        # Create new schema with metadata fields
        all_fields = list(schema.fields) + metadata_fields
        return Schema(*all_fields)

    def get_default_partition_spec(self, schema: Optional[Schema] = None) -> PartitionSpec:
        """
        Get default partition specification for bronze tables.

        Partitions by day(ingestion_timestamp) for efficient querying
        and data lifecycle management.

        Args:
            schema: Table schema (optional, for validation)

        Returns:
            Partition specification
        """
        # Bronze tables are partitioned by ingestion date
        partition_field = PartitionField(
            source_id=1001,  # ingestion_timestamp field ID
            field_id=1000,
            transform=DayTransform(),
            name="ingestion_date",
        )

        return PartitionSpec(partition_field)

    def create_table(
        self,
        table_name: str,
        schema: Schema,
        add_metadata: bool = True,
        properties: Optional[Dict[str, str]] = None,
    ) -> Table:
        """
        Create a bronze layer table.

        Args:
            table_name: Name of the table
            schema: Table schema
            add_metadata: Whether to add audit metadata columns
            properties: Additional table properties

        Returns:
            Created Iceberg table

        Raises:
            StorageError: If table creation fails
        """
        try:
            logger.info(
                "Creating bronze table",
                table=table_name,
                layer=self.LAYER_NAME,
            )

            # Add metadata columns if requested
            if add_metadata:
                schema = self._add_metadata_fields(schema)

            # Build full table identifier
            table_identifier = f"{self.LAYER_NAME}.{table_name}"

            # Set bronze-specific properties
            bronze_properties = {
                "write.format.default": "parquet",
                "write.parquet.compression-codec": "snappy",
                "commit.retry.num-retries": "3",
                "layer": self.LAYER_NAME,
                "retention.days": str(self.DEFAULT_RETENTION_DAYS),
            }

            if properties:
                bronze_properties.update(properties)

            # Get partition spec
            partition_spec = self.get_default_partition_spec(schema)

            # Create table
            table = self.table_manager.create_table(
                table_identifier, schema, partition_spec, bronze_properties
            )

            logger.info(
                "Bronze table created successfully",
                table=table_identifier,
                schema=str(schema),
            )

            return table

        except Exception as e:
            logger.error(f"Failed to create bronze table {table_name}: {e}")
            raise StorageError(f"Failed to create bronze table: {e}")

    @ingestion_duration_seconds.labels(source="unknown", layer="bronze").time()
    def ingest_raw_data(
        self,
        table_name: str,
        data: Union[List[Dict[str, Any]], pa.Table],
        source_system: Optional[str] = None,
        source_file: Optional[str] = None,
        add_metadata: bool = True,
    ) -> int:
        """
        Ingest raw data into bronze layer.

        Args:
            table_name: Target table name
            data: Data to ingest (list of dicts or PyArrow table)
            source_system: Source system identifier
            source_file: Source file name or identifier
            add_metadata: Whether to add metadata columns

        Returns:
            Number of records ingested

        Raises:
            IngestionError: If ingestion fails
        """
        try:
            logger.info(
                "Ingesting data to bronze layer",
                table=table_name,
                layer=self.LAYER_NAME,
            )

            # Convert to PyArrow table if needed
            if isinstance(data, list):
                arrow_table = pa.Table.from_pylist(data)
            else:
                arrow_table = data

            record_count = len(arrow_table)

            # Add metadata columns if requested
            if add_metadata:
                arrow_table = self._add_metadata_to_data(
                    arrow_table, source_system, source_file
                )

            # Build full table identifier
            table_identifier = f"{self.LAYER_NAME}.{table_name}"

            # Append data
            self.table_manager.append_data(table_identifier, arrow_table)

            # Update metrics
            ingestion_records_total.labels(
                source=source_system or "unknown",
                layer=self.LAYER_NAME,
                status="success",
            ).inc(record_count)

            ingestion_bytes_total.labels(
                source=source_system or "unknown", layer=self.LAYER_NAME
            ).inc(arrow_table.nbytes)

            logger.info(
                "Data ingested successfully",
                table=table_identifier,
                records=record_count,
                size_mb=arrow_table.nbytes / (1024 * 1024),
            )

            return record_count

        except Exception as e:
            logger.error(f"Failed to ingest data to {table_name}: {e}")
            ingestion_records_total.labels(
                source=source_system or "unknown",
                layer=self.LAYER_NAME,
                status="failure",
            ).inc(1)
            raise IngestionError(f"Failed to ingest data: {e}")

    def _add_metadata_to_data(
        self,
        arrow_table: pa.Table,
        source_system: Optional[str],
        source_file: Optional[str],
    ) -> pa.Table:
        """
        Add metadata columns to data.

        Args:
            arrow_table: Data table
            source_system: Source system identifier
            source_file: Source file identifier

        Returns:
            Table with metadata columns added
        """
        num_rows = len(arrow_table)
        current_timestamp = int(datetime.utcnow().timestamp() * 1000)

        # Add ingestion timestamp
        ingestion_timestamps = pa.array([current_timestamp] * num_rows, type=pa.int64())

        # Add source system
        source_systems = pa.array(
            [source_system or "unknown"] * num_rows, type=pa.string()
        )

        # Add source file
        source_files = pa.array(
            [source_file or ""] * num_rows, type=pa.string()
        )

        # Add record hash for deduplication
        record_hashes = self._compute_record_hashes(arrow_table)

        # Combine with original data
        metadata_table = pa.Table.from_arrays(
            [ingestion_timestamps, source_systems, source_files, record_hashes],
            names=[
                "ingestion_timestamp",
                "source_system",
                "source_file",
                "record_hash",
            ],
        )

        # Concatenate horizontally
        combined = pa.concat_tables([arrow_table, metadata_table], promote=True)

        return combined

    def _compute_record_hashes(self, arrow_table: pa.Table) -> pa.Array:
        """
        Compute hash for each record for deduplication.

        Args:
            arrow_table: Data table

        Returns:
            Array of record hashes
        """
        hashes = []

        for i in range(len(arrow_table)):
            row = arrow_table.slice(i, 1).to_pydict()
            # Convert row to string and hash
            row_str = str(sorted(row.items()))
            row_hash = hashlib.md5(row_str.encode()).hexdigest()
            hashes.append(row_hash)

        return pa.array(hashes, type=pa.string())

    def read_data(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        filter_expr: Optional[Any] = None,
    ) -> pa.Table:
        """
        Read data from bronze table.

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
                "Reading from bronze table",
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
            logger.error(f"Failed to read from bronze table {table_name}: {e}")
            raise StorageError(f"Failed to read data: {e}")

    def get_table_stats(self, table_name: str) -> Dict[str, Any]:
        """
        Get statistics for a bronze table.

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

            # Add bronze-specific stats
            stats["layer"] = self.LAYER_NAME
            stats["retention_days"] = self.DEFAULT_RETENTION_DAYS

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {table_name}: {e}")
            raise StorageError(f"Failed to get table stats: {e}")

    def list_tables(self) -> List[str]:
        """
        List all tables in bronze layer.

        Returns:
            List of table names
        """
        return self.catalog_manager.list_tables(self.LAYER_NAME)
