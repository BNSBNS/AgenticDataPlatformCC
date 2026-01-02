"""
Time Travel Operations

Provides time travel capabilities for Iceberg tables.
"""

from datetime import datetime
from typing import Optional, Union

import pyarrow as pa
from pyiceberg.table import Table

from src.common.exceptions import IcebergError
from src.common.logging import get_logger
from src.lakehouse.iceberg.catalog import IcebergCatalogManager

logger = get_logger(__name__)


class TimeTravelManager:
    """
    Manages time travel operations for Iceberg tables.
    """

    def __init__(self, catalog_manager: Optional['IcebergCatalogManager'] = None):
        """
        Initialize time travel manager.

        Args:
            catalog_manager: Iceberg catalog manager
        """
        from src.lakehouse.iceberg.catalog import get_catalog_manager

        self.catalog_manager = catalog_manager or get_catalog_manager()

    def read_at_snapshot(
        self,
        table: Union[Table, str],
        snapshot_id: int,
        columns: Optional[list] = None,
    ) -> pa.Table:
        """
        Read table data at a specific snapshot.

        Args:
            table: Iceberg table or table identifier
            snapshot_id: Snapshot ID to read from
            columns: Columns to select

        Returns:
            PyArrow table with data from snapshot

        Raises:
            IcebergError: If operation fails
        """
        try:
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            logger.info(
                "Reading table at snapshot",
                table=str(table.name()),
                snapshot_id=snapshot_id,
            )

            # Read at specific snapshot
            scan = table.scan(snapshot_id=snapshot_id)

            if columns:
                scan = scan.select(*columns)

            data = scan.to_arrow()

            logger.info(
                "Snapshot read successful",
                table=str(table.name()),
                snapshot_id=snapshot_id,
                rows=len(data),
            )

            return data

        except Exception as e:
            logger.error("Failed to read snapshot", error=str(e))
            raise IcebergError(f"Failed to read snapshot: {str(e)}")

    def read_at_timestamp(
        self,
        table: Union[Table, str],
        timestamp: datetime,
        columns: Optional[list] = None,
    ) -> pa.Table:
        """
        Read table data as it existed at a specific timestamp.

        Args:
            table: Iceberg table or table identifier
            timestamp: Timestamp to read from
            columns: Columns to select

        Returns:
            PyArrow table with historical data

        Raises:
            IcebergError: If operation fails
        """
        try:
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            # Find snapshot closest to timestamp
            target_ms = int(timestamp.timestamp() * 1000)
            snapshots = list(table.snapshots())

            # Find snapshot <= target timestamp
            valid_snapshots = [
                s for s in snapshots if s.timestamp_ms <= target_ms
            ]

            if not valid_snapshots:
                raise IcebergError(f"No snapshot found before {timestamp}")

            # Get closest snapshot
            snapshot = max(valid_snapshots, key=lambda s: s.timestamp_ms)

            logger.info(
                "Reading table at timestamp",
                table=str(table.name()),
                timestamp=timestamp.isoformat(),
                snapshot_id=snapshot.snapshot_id,
            )

            return self.read_at_snapshot(table, snapshot.snapshot_id, columns)

        except Exception as e:
            logger.error("Failed to read at timestamp", error=str(e))
            raise IcebergError(f"Failed to read at timestamp: {str(e)}")

    def rollback_to_snapshot(
        self,
        table: Union[Table, str],
        snapshot_id: int,
    ) -> None:
        """
        Rollback table to a previous snapshot.

        Args:
            table: Iceberg table or table identifier
            snapshot_id: Snapshot ID to rollback to

        Raises:
            IcebergError: If operation fails
        """
        try:
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            logger.info(
                "Rolling back table to snapshot",
                table=str(table.name()),
                snapshot_id=snapshot_id,
            )

            # Rollback to snapshot
            table.rollback_to_snapshot(snapshot_id)

            logger.info(
                "Rollback successful",
                table=str(table.name()),
                snapshot_id=snapshot_id,
            )

        except Exception as e:
            logger.error("Failed to rollback table", error=str(e))
            raise IcebergError(f"Failed to rollback table: {str(e)}")

    def list_snapshots(self, table: Union[Table, str]) -> list:
        """
        List all snapshots for a table.

        Args:
            table: Iceberg table or table identifier

        Returns:
            List of snapshot information

        Raises:
            IcebergError: If operation fails
        """
        try:
            if isinstance(table, str):
                table = self.catalog_manager.load_table(table)

            snapshots = []
            for snapshot in table.snapshots():
                snapshots.append(
                    {
                        "snapshot_id": snapshot.snapshot_id,
                        "timestamp_ms": snapshot.timestamp_ms,
                        "timestamp": datetime.fromtimestamp(
                            snapshot.timestamp_ms / 1000
                        ).isoformat(),
                        "manifest_list": snapshot.manifest_list,
                    }
                )

            return snapshots

        except Exception as e:
            logger.error("Failed to list snapshots", error=str(e))
            raise IcebergError(f"Failed to list snapshots: {str(e)}")
