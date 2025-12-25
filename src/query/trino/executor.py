"""
Trino query executor for federated queries across lakehouse.
"""

from typing import List, Dict, Any, Optional
from trino.dbapi import connect
from trino.auth import BasicAuthentication

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import QueryError
from src.common.metrics import query_execution_total, query_duration_seconds

logger = get_logger(__name__)


class TrinoQueryExecutor:
    """
    Execute queries using Trino for federated lakehouse access.

    Supports querying Iceberg tables across Bronze/Silver/Gold layers.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 8080,
        user: str = "admin",
        catalog: str = "iceberg",
    ):
        """
        Initialize Trino query executor.

        Args:
            host: Trino coordinator host
            port: Trino coordinator port
            user: Authentication user
            catalog: Default catalog
        """
        self.config = get_config()
        self.host = host or "localhost"
        self.port = port
        self.user = user
        self.catalog = catalog

        logger.info(
            "Trino query executor initialized",
            host=self.host,
            catalog=self.catalog,
        )

    def execute(
        self,
        query: str,
        schema: str = "default",
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a SQL query.

        Args:
            query: SQL query string
            schema: Schema to use
            params: Query parameters

        Returns:
            List of result rows as dictionaries

        Raises:
            QueryError: If query execution fails
        """
        try:
            logger.info("Executing Trino query", query=query[:100])

            # Connect to Trino
            conn = connect(
                host=self.host,
                port=self.port,
                user=self.user,
                catalog=self.catalog,
                schema=schema,
            )

            cursor = conn.cursor()

            # Execute query
            with query_duration_seconds.labels(
                engine="trino", query_type="select"
            ).time():
                cursor.execute(query, params)

                # Fetch results
                columns = [desc[0] for desc in cursor.description]
                results = []

                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))

            # Record metrics
            query_execution_total.labels(engine="trino", status="success").inc()

            logger.info(f"Query returned {len(results)} rows")

            cursor.close()
            conn.close()

            return results

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            query_execution_total.labels(engine="trino", status="error").inc()
            raise QueryError(f"Trino query failed: {e}")

    def execute_to_dataframe(self, query: str, schema: str = "default"):
        """
        Execute query and return results as pandas DataFrame.

        Args:
            query: SQL query
            schema: Schema to use

        Returns:
            pandas DataFrame with results
        """
        import pandas as pd

        results = self.execute(query, schema)
        return pd.DataFrame(results)
