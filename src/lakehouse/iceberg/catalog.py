"""
Apache Iceberg Catalog Management

Manages Iceberg catalog initialization, namespace management, and catalog operations.
Supports REST catalog, Glue catalog, and Hive catalog.
"""

from typing import Dict, List, Optional

import pyarrow as pa
from pyiceberg.catalog import Catalog, load_catalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, NoSuchNamespaceError
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.types import (
    BooleanType,
    DateType,
    DoubleType,
    LongType,
    NestedField,
    StringType,
    TimestampType,
)

from src.common.config import get_config
from src.common.exceptions import CatalogError, IcebergError
from src.common.logging import get_logger

logger = get_logger(__name__)


class IcebergCatalogManager:
    """
    Manages Apache Iceberg catalog operations.

    Supports:
    - Multiple catalog types (REST, Glue, Hive)
    - Namespace management
    - Table discovery
    - Catalog metadata
    """

    def __init__(self, catalog_name: str = "default"):
        """
        Initialize Iceberg catalog manager.

        Args:
            catalog_name: Name of the catalog to manage
        """
        self.config = get_config()
        self.catalog_name = catalog_name
        self.catalog: Optional[Catalog] = None
        self._initialize_catalog()

    def _initialize_catalog(self) -> None:
        """Initialize the Iceberg catalog based on configuration."""
        try:
            catalog_config = self._get_catalog_config()

            logger.info(
                "Initializing Iceberg catalog",
                catalog_name=self.catalog_name,
                catalog_type=self.config.iceberg_catalog_type.value,
            )

            self.catalog = load_catalog(self.catalog_name, **catalog_config)

            logger.info("Iceberg catalog initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize Iceberg catalog", error=str(e))
            raise CatalogError(f"Failed to initialize catalog: {str(e)}")

    def _get_catalog_config(self) -> Dict:
        """
        Get catalog configuration based on catalog type.

        Returns:
            Catalog configuration dictionary
        """
        if self.config.iceberg_catalog_type.value == "rest":
            return {
                "type": "rest",
                "uri": self.config.iceberg_catalog_uri,
                "warehouse": self.config.iceberg_warehouse_location,
                "s3.endpoint": self.config.get_storage_endpoint(),
                "s3.access-key-id": self.config.storage_access_key,
                "s3.secret-access-key": self.config.storage_secret_key,
                "s3.path-style-access": "true",
            }
        elif self.config.iceberg_catalog_type.value == "glue":
            return {
                "type": "glue",
                "warehouse": self.config.iceberg_warehouse_location,
                "catalog-id": self.config.iceberg_glue_catalog_id,
                "region": self.config.iceberg_glue_region,
            }
        elif self.config.iceberg_catalog_type.value == "hive":
            return {
                "type": "hive",
                "uri": self.config.iceberg_catalog_uri,
                "warehouse": self.config.iceberg_warehouse_location,
            }
        else:
            raise CatalogError(
                f"Unsupported catalog type: {self.config.iceberg_catalog_type}"
            )

    def create_namespace(
        self, namespace: str, properties: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Create a new namespace (database) in the catalog.

        Args:
            namespace: Namespace name (e.g., 'bronze', 'silver', 'gold')
            properties: Optional namespace properties

        Raises:
            CatalogError: If namespace creation fails
        """
        try:
            if properties is None:
                properties = {}

            logger.info("Creating namespace", namespace=namespace)

            self.catalog.create_namespace(namespace, properties)

            logger.info("Namespace created successfully", namespace=namespace)

        except NamespaceAlreadyExistsError:
            logger.warning("Namespace already exists", namespace=namespace)
        except Exception as e:
            logger.error("Failed to create namespace", namespace=namespace, error=str(e))
            raise CatalogError(f"Failed to create namespace {namespace}: {str(e)}")

    def drop_namespace(self, namespace: str) -> None:
        """
        Drop a namespace from the catalog.

        Args:
            namespace: Namespace name to drop

        Raises:
            CatalogError: If namespace deletion fails
        """
        try:
            logger.info("Dropping namespace", namespace=namespace)

            self.catalog.drop_namespace(namespace)

            logger.info("Namespace dropped successfully", namespace=namespace)

        except NoSuchNamespaceError:
            logger.warning("Namespace does not exist", namespace=namespace)
        except Exception as e:
            logger.error("Failed to drop namespace", namespace=namespace, error=str(e))
            raise CatalogError(f"Failed to drop namespace {namespace}: {str(e)}")

    def list_namespaces(self) -> List[str]:
        """
        List all namespaces in the catalog.

        Returns:
            List of namespace names

        Raises:
            CatalogError: If listing fails
        """
        try:
            namespaces = self.catalog.list_namespaces()
            return [str(ns) for ns in namespaces]

        except Exception as e:
            logger.error("Failed to list namespaces", error=str(e))
            raise CatalogError(f"Failed to list namespaces: {str(e)}")

    def list_tables(self, namespace: str) -> List[str]:
        """
        List all tables in a namespace.

        Args:
            namespace: Namespace to list tables from

        Returns:
            List of table names

        Raises:
            CatalogError: If listing fails
        """
        try:
            tables = self.catalog.list_tables(namespace)
            return [str(table) for table in tables]

        except Exception as e:
            logger.error(
                "Failed to list tables", namespace=namespace, error=str(e)
            )
            raise CatalogError(
                f"Failed to list tables in namespace {namespace}: {str(e)}"
            )

    def load_table(self, table_identifier: str) -> Table:
        """
        Load a table from the catalog.

        Args:
            table_identifier: Table identifier (e.g., 'bronze.events' or 'events')

        Returns:
            Iceberg Table object

        Raises:
            IcebergError: If table loading fails
        """
        try:
            logger.info("Loading table", table=table_identifier)

            table = self.catalog.load_table(table_identifier)

            logger.info(
                "Table loaded successfully",
                table=table_identifier,
                schema=str(table.schema()),
            )

            return table

        except Exception as e:
            logger.error("Failed to load table", table=table_identifier, error=str(e))
            raise IcebergError(f"Failed to load table {table_identifier}: {str(e)}")

    def table_exists(self, table_identifier: str) -> bool:
        """
        Check if a table exists in the catalog.

        Args:
            table_identifier: Table identifier

        Returns:
            True if table exists, False otherwise
        """
        try:
            self.catalog.load_table(table_identifier)
            return True
        except Exception:
            return False

    def drop_table(self, table_identifier: str) -> None:
        """
        Drop a table from the catalog.

        Args:
            table_identifier: Table identifier to drop

        Raises:
            IcebergError: If table deletion fails
        """
        try:
            logger.info("Dropping table", table=table_identifier)

            self.catalog.drop_table(table_identifier)

            logger.info("Table dropped successfully", table=table_identifier)

        except Exception as e:
            logger.error("Failed to drop table", table=table_identifier, error=str(e))
            raise IcebergError(f"Failed to drop table {table_identifier}: {str(e)}")

    def initialize_medallion_namespaces(self) -> None:
        """
        Initialize the medallion architecture namespaces (bronze, silver, gold).

        Creates three namespaces with appropriate properties.
        """
        medallion_layers = [
            {
                "name": "bronze",
                "properties": {
                    "description": "Raw, immutable data layer",
                    "retention_days": str(self.config.data_retention_days_bronze),
                    "layer": "bronze",
                },
            },
            {
                "name": "silver",
                "properties": {
                    "description": "Validated, refined data layer",
                    "retention_days": str(self.config.data_retention_days_silver),
                    "layer": "silver",
                },
            },
            {
                "name": "gold",
                "properties": {
                    "description": "Curated, business-ready data layer",
                    "retention_days": str(self.config.data_retention_days_gold),
                    "layer": "gold",
                },
            },
        ]

        for layer in medallion_layers:
            self.create_namespace(layer["name"], layer["properties"])

        logger.info("Medallion architecture namespaces initialized")

    def get_catalog_stats(self) -> Dict:
        """
        Get catalog statistics.

        Returns:
            Dictionary with catalog statistics
        """
        stats = {
            "catalog_name": self.catalog_name,
            "catalog_type": self.config.iceberg_catalog_type.value,
            "warehouse_location": self.config.iceberg_warehouse_location,
            "namespaces": {},
        }

        try:
            namespaces = self.list_namespaces()
            stats["namespace_count"] = len(namespaces)

            for namespace in namespaces:
                tables = self.list_tables(namespace)
                stats["namespaces"][namespace] = {
                    "table_count": len(tables),
                    "tables": tables,
                }

        except Exception as e:
            logger.error("Failed to get catalog stats", error=str(e))

        return stats


# Convenience function for getting default catalog manager
_default_catalog_manager: Optional[IcebergCatalogManager] = None


def get_catalog_manager() -> IcebergCatalogManager:
    """
    Get the default catalog manager instance (singleton).

    Returns:
        IcebergCatalogManager instance
    """
    global _default_catalog_manager

    if _default_catalog_manager is None:
        _default_catalog_manager = IcebergCatalogManager()

    return _default_catalog_manager
