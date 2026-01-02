"""
Model Context Protocol (MCP) integration.

Provides MCP servers for agent access to the data platform.
"""

from src.mcp.servers.data_server import DataMCPServer
from src.mcp.servers.metadata_server import MetadataMCPServer

__all__ = [
    "DataMCPServer",
    "MetadataMCPServer",
]
