"""
Spark session manager for batch processing.
"""

from typing import Optional, Dict, Any
from pyspark.sql import SparkSession

from src.common.config import get_config
from src.common.logging import get_logger

logger = get_logger(__name__)


class SparkSessionManager:
    """
    Manage Spark sessions for batch data processing.

    Provides configured Spark sessions with Iceberg support.
    """

    def __init__(self, app_name: str = "DataPlatform"):
        """
        Initialize Spark session manager.

        Args:
            app_name: Application name
        """
        self.config = get_config()
        self.app_name = app_name
        self._session: Optional[SparkSession] = None

        logger.info("Spark session manager initialized", app_name=app_name)

    def get_session(self) -> SparkSession:
        """
        Get or create Spark session.

        Returns:
            Configured Spark session
        """
        if self._session is None:
            self._session = (
                SparkSession.builder.appName(self.app_name)
                .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
                .config("spark.sql.catalog.iceberg", "org.apache.iceberg.spark.SparkCatalog")
                .config("spark.sql.catalog.iceberg.type", "hadoop")
                .config("spark.sql.catalog.iceberg.warehouse", self.config.storage_bucket_bronze)
                .getOrCreate()
            )

            logger.info("Spark session created")

        return self._session

    def stop(self):
        """Stop Spark session."""
        if self._session:
            self._session.stop()
            self._session = None
            logger.info("Spark session stopped")
