"""
MCP Data Server for agent access to lakehouse data.
"""

from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.query.trino.executor import TrinoQueryExecutor
from src.lakehouse.medallion.gold_layer import GoldLayer
from src.common.logging import get_logger
from src.common.metrics import mcp_requests_total

logger = get_logger(__name__)


class QueryRequest(BaseModel):
    """MCP query request model."""
    query: str
    schema: Optional[str] = "default"
    limit: Optional[int] = 100


class DataMCPServer:
    """
    MCP server for data access.

    Provides tools for agents to query and access lakehouse data.
    """

    def __init__(self):
        """Initialize MCP data server."""
        self.app = FastAPI(title="Data Platform MCP Server")
        self.query_executor = TrinoQueryExecutor()
        self.gold_layer = GoldLayer()

        # Register endpoints
        self._register_endpoints()

        logger.info("Data MCP server initialized")

    def _register_endpoints(self):
        """Register MCP endpoints."""

        @self.app.post("/tools/query")
        async def execute_query(request: QueryRequest) -> Dict[str, Any]:
            """
            Execute SQL query against lakehouse.

            Args:
                request: Query request

            Returns:
                Query results
            """
            try:
                # Record metric
                mcp_requests_total.labels(
                    server="data", method="query", status="success"
                ).inc()

                results = self.query_executor.execute(
                    query=request.query,
                    schema=request.schema,
                )

                # Limit results
                if request.limit:
                    results = results[:request.limit]

                return {
                    "success": True,
                    "results": results,
                    "count": len(results),
                }

            except Exception as e:
                mcp_requests_total.labels(
                    server="data", method="query", status="error"
                ).inc()

                logger.error(f"Query failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/resources/tables")
        async def list_tables(layer: str = "gold") -> Dict[str, Any]:
            """
            List available tables.

            Args:
                layer: Data layer (bronze, silver, gold)

            Returns:
                List of table names
            """
            try:
                mcp_requests_total.labels(
                    server="data", method="list_tables", status="success"
                ).inc()

                if layer == "gold":
                    tables = self.gold_layer.list_tables()
                else:
                    tables = []

                return {
                    "success": True,
                    "layer": layer,
                    "tables": tables,
                }

            except Exception as e:
                mcp_requests_total.labels(
                    server="data", method="list_tables", status="error"
                ).inc()

                logger.error(f"List tables failed: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """
        Run MCP server.

        Args:
            host: Host to bind
            port: Port to listen on
        """
        import uvicorn
        uvicorn.run(self.app, host=host, port=port)
