"""
MCP Metadata Server for catalog and lineage access.
"""

from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException

from src.lakehouse.iceberg.catalog import IcebergCatalogManager
from src.governance.lineage.tracker import LineageTracker
from src.common.logging import get_logger
from src.common.metrics import mcp_requests_total

logger = get_logger(__name__)


class MetadataMCPServer:
    """
    MCP server for metadata access.

    Provides tools for agents to explore catalog and lineage.
    """

    def __init__(self):
        """Initialize MCP metadata server."""
        self.app = FastAPI(title="Metadata MCP Server")
        self.catalog = IcebergCatalogManager()
        self.lineage = LineageTracker()

        # Register endpoints
        self._register_endpoints()

        logger.info("Metadata MCP server initialized")

    def _register_endpoints(self):
        """Register MCP endpoints."""

        @self.app.get("/resources/namespaces")
        async def list_namespaces() -> Dict[str, Any]:
            """
            List all namespaces in catalog.

            Returns:
                List of namespace names
            """
            try:
                mcp_requests_total.labels(
                    server="metadata", method="list_namespaces", status="success"
                ).inc()

                namespaces = self.catalog.list_namespaces()

                return {
                    "success": True,
                    "namespaces": namespaces,
                }

            except Exception as e:
                mcp_requests_total.labels(
                    server="metadata", method="list_namespaces", status="error"
                ).inc()

                logger.error(f"List namespaces failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/resources/tables/{namespace}")
        async def list_tables(namespace: str) -> Dict[str, Any]:
            """
            List tables in namespace.

            Args:
                namespace: Namespace name

            Returns:
                List of table names
            """
            try:
                mcp_requests_total.labels(
                    server="metadata", method="list_tables", status="success"
                ).inc()

                tables = self.catalog.list_tables(namespace)

                return {
                    "success": True,
                    "namespace": namespace,
                    "tables": tables,
                }

            except Exception as e:
                mcp_requests_total.labels(
                    server="metadata", method="list_tables", status="error"
                ).inc()

                logger.error(f"List tables failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def run(self, host: str = "0.0.0.0", port: int = 8001):
        """
        Run MCP server.

        Args:
            host: Host to bind
            port: Port to listen on
        """
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)
