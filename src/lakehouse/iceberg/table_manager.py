"""
Apache Iceberg Table Manager

Manages Iceberg table creation, writes, reads, and schema operations.
"""

from typing import Any, Dict, List, Optional, Union

import pyarrow as pa
import pyarrow.compute as pc
from pyiceberg.expressions import AlwaysTrue
from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.transforms import DayTransform, HourTransform, MonthTransform, YearTransform

from src.common.exceptions import IcebergError
from src.common.logging import get_logger
from src.common.metrics import (
    storage_table_files_count,
    storage_table_rows_count,
    storage_table_size_bytes,
    storage_write_duration_seconds,
)
from src.lakehouse.iceberg.catalog import IcebergCatalogManager

logger = get_logger(__name__)


class IcebergTableManager:
    """
    Manages Iceberg table operations including CRUD, schema evolution, and partitioning.
    """

    def __init__(self, catalog_manager: Optional[IcebergCatalogManager] = None):
        """
        Initialize table manager.

        Args:
            catalog_manager: Iceberg catalog manager (uses default if None)
        """
        from src.lakehouse.iceberg.catalog import get_catalog_manager

        self.catalog_manager = catalog_manager or get_catalog_manager()
        self.catalog = self.catalog_manager.catalog

    def create_table(
        self,
        table_identifier: str,
        schema: Schema,
        partition_spec: Optional[PartitionSpec] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> Table:
        """
        Create a new Iceberg table.

        Args:
            table_identifier: Table identifier (namespace.table_name)
            schema: Iceberg schema
            partition_spec: Partition specification
            properties: Table properties

        Returns:
            Created Iceberg table

        Raises:
            IcebergError: If table creation fails
        """
        try:
            logger.info("Creating Iceberg table", table=table_identifier)

            table = self.catalog.create_table(
                identifier=table_identifier,
                schema=schema,
                partition_spec=partition_spec,
                properties=properties or {},
            )

            logger.info(
                "Table created successfully",
                table=table_identifier,
                schema=str(schema),
                partitions=str(partition_spec) if partition_spec else "none",
            )

            return table

        except Exception as e:
            logger.error(
                "Failed to create table", table=table_identifier, error=str(e)
            )
            raise IcebergError(f"Failed to create table {table_identifier}: {str(e)}")

    def create_partitioned_table(
        self,
        table_identifier: str,
        schema: Schema,
        partition_by: List[Dict[str, str]],
        properties: Optional[Dict[str, str]] = None,
    ) -> Table:
        """
        Create a partitioned Iceberg table.

        Args:
            table_identifier: Table identifier
            schema: Iceberg schema
            partition_by: List of partition specifications
                Example: [{"field": "event_date", "transform": "day"}]
            properties: Table properties

        Returns:
            Created Iceberg table
        """
        try:
            # Build partition spec
            partition_fields = []
            for partition_config in partition_by:
                field_name = partition_config["field"]
                transform = partition_config["transform"]

                # Get source field ID from schema
                source_field = next(
                    (f for f in schema.fields if f.name == field_name), None
                )
                if not source_field:
                    raise IcebergError(f"Partition field {field_name} not found in schema")

                # Map transform string to Iceberg transform
                transform_map = {
                    "identity": None,  # No transform
                    "year": YearTransform(),
                    "month": MonthTransform(),
                    "day": DayTransform(),
                    "hour": HourTransform(),
                }

                if transform not in transform_map:
                    raise IcebergError(f"Unsupported transform: {transform}")

                transform_obj = transform_map[transform]

                if transform_obj:
                    partition_field = PartitionField(
                        source_id=source_field.field_id,
                        field_id=1000 + len(partition_fields),
                        transform=transform_obj,
                        name=f"{field_name}_{transform}",
                    )
                    partition_fields.append(partition_field)

            partition_spec = PartitionSpec(*partition_fields) if partition_fields else None

            return self.create_table(
                table_identifier, schema, partition_spec, properties
            )

        except Exception as e:
            logger.error(
                "Failed to create partitioned table",
                table=table_identifier,
                error=str(e),
            )
            raise IcebergError(
                f"Failed to create partitioned table {table_identifier}: {str(e)}"
            )

    @storage_write_duration_seconds.labels(layer="unknown", operation="append").time()
    def append_data(
        self,
        table: Union[Table, str],
        data: Union[pa.Table, List[Dict[str, Any]]],
    ) -> None:
        """
        Append data to an Iceberg table.

        Args:
            table: Iceberg table or table identifier
            data: Data to append (PyArrow Table or list of dictionaries)

        Raises:
            IcebergError: If append operation fails
        """
        try:
            # Load table if identifier provided
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            # Convert data to PyArrow table if needed
            if isinstance(data, list):
                data = pa.Table.from_pylist(data)

            logger.info(
                "Appending data to table",
                table=str(table.name()),
                rows=len(data),
                size_mb=data.nbytes / (1024 * 1024),
            )

            # Append data
            table.append(data)

            logger.info(
                "Data appended successfully",
                table=str(table.name()),
                rows=len(data),
            )

            # Update metrics
            storage_table_rows_count.labels(
                layer="unknown",
                namespace=str(table.name()).split(".")[0],
                table=str(table.name()).split(".")[-1],
            ).set(len(data))

        except Exception as e:
            logger.error("Failed to append data", table=str(table), error=str(e))
            raise IcebergError(f"Failed to append data to table: {str(e)}")

    def read_table(
        self,
        table: Union[Table, str],
        columns: Optional[List[str]] = None,
        row_filter: Optional[Any] = None,
        limit: Optional[int] = None,
    ) -> pa.Table:
        """
        Read data from an Iceberg table.

        Args:
            table: Iceberg table or table identifier
            columns: Columns to select (None = all columns)
            row_filter: Iceberg expression for filtering rows
            limit: Maximum number of rows to return

        Returns:
            PyArrow Table with query results

        Raises:
            IcebergError: If read operation fails
        """
        try:
            # Load table if identifier provided
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            logger.info("Reading from table", table=str(table.name()))

            # Build scan
            scan = table.scan()

            if columns:
                scan = scan.select(*columns)

            if row_filter:
                scan = scan.filter(row_filter)
            else:
                scan = scan.filter(AlwaysTrue())

            # Execute scan
            arrow_table = scan.to_arrow()

            # Apply limit if specified
            if limit and len(arrow_table) > limit:
                arrow_table = arrow_table.slice(0, limit)

            logger.info(
                "Data read successfully",
                table=str(table.name()),
                rows=len(arrow_table),
                columns=arrow_table.num_columns,
            )

            return arrow_table

        except Exception as e:
            logger.error("Failed to read table", table=str(table), error=str(e))
            raise IcebergError(f"Failed to read table: {str(e)}")

    def overwrite_data(
        self,
        table: Union[Table, str],
        data: Union[pa.Table, List[Dict[str, Any]]],
    ) -> None:
        """
        Overwrite table data (replaces all existing data).

        Args:
            table: Iceberg table or table identifier
            data: New data

        Raises:
            IcebergError: If overwrite operation fails
        """
        try:
            # Load table if identifier provided
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            # Convert data to PyArrow table if needed
            if isinstance(data, list):
                data = pa.Table.from_pylist(data)

            logger.info(
                "Overwriting table data",
                table=str(table.name()),
                rows=len(data),
            )

            # Overwrite data
            table.overwrite(data)

            logger.info(
                "Table overwritten successfully",
                table=str(table.name()),
                rows=len(data),
            )

        except Exception as e:
            logger.error("Failed to overwrite table", table=str(table), error=str(e))
            raise IcebergError(f"Failed to overwrite table: {str(e)}")

    def get_table_metadata(self, table: Union[Table, str]) -> Dict:
        """
        Get table metadata and statistics.

        Args:
            table: Iceberg table or table identifier

        Returns:
            Dictionary with table metadata
        """
        try:
            # Load table if identifier provided
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            metadata = {
                "name": str(table.name()),
                "schema": str(table.schema()),
                "partition_spec": str(table.spec()),
                "properties": table.properties,
                "location": table.location(),
                "snapshots": [],
            }

            # Get snapshot information
            for snapshot in table.snapshots():
                metadata["snapshots"].append(
                    {
                        "snapshot_id": snapshot.snapshot_id,
                        "timestamp_ms": snapshot.timestamp_ms,
                        "manifest_list": snapshot.manifest_list,
                    }
                )

            # Get current snapshot
            current_snapshot = table.current_snapshot()
            if current_snapshot:
                metadata["current_snapshot_id"] = current_snapshot.snapshot_id

            # Get table statistics
            scan = table.scan()
            stats = scan.to_arrow()
            metadata["row_count"] = len(stats)
            metadata["size_bytes"] = stats.nbytes

            # Update Prometheus metrics
            namespace = str(table.name()).split(".")[0]
            table_name = str(table.name()).split(".")[-1]

            storage_table_rows_count.labels(
                layer=namespace, namespace=namespace, table=table_name
            ).set(metadata["row_count"])

            storage_table_size_bytes.labels(
                layer=namespace, namespace=namespace, table=table_name
            ).set(metadata["size_bytes"])

            return metadata

        except Exception as e:
            logger.error(
                "Failed to get table metadata", table=str(table), error=str(e)
            )
            raise IcebergError(f"Failed to get table metadata: {str(e)}")

    def delete_data(
        self,
        table: Union[Table, str],
        row_filter: Any,
    ) -> None:
        """
        Delete data from table matching filter.

        Args:
            table: Iceberg table or table identifier
            row_filter: Iceberg expression for rows to delete

        Raises:
            IcebergError: If delete operation fails
        """
        try:
            # Load table if identifier provided
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            logger.info(
                "Deleting data from table",
                table=str(table.name()),
                filter=str(row_filter),
            )

            # Delete matching rows
            table.delete(row_filter)

            logger.info("Data deleted successfully", table=str(table.name()))

        except Exception as e:
            logger.error("Failed to delete data", table=str(table), error=str(e))
            raise IcebergError(f"Failed to delete data from table: {str(e)}")

    def compact_table(self, table: Union[Table, str]) -> None:
        """
        Compact table data files.

        Args:
            table: Iceberg table or table identifier

        Raises:
            IcebergError: If compaction fails
        """
        try:
            # Load table if identifier provided
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            logger.info("Compacting table", table=str(table.name()))

            # Note: Full compaction implementation would use Spark or Flink
            # This is a placeholder for the operation
            logger.warning(
                "Compaction requires Spark/Flink job - operation logged but not executed"
            )

        except Exception as e:
            logger.error("Failed to compact table", table=str(table), error=str(e))
            raise IcebergError(f"Failed to compact table: {str(e)}")
