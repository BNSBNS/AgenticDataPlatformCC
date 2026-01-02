"""
Metrics Collection

Prometheus metrics for monitoring the data platform.
"""

from functools import wraps
from time import time
from typing import Callable, Optional

from prometheus_client import Counter, Gauge, Histogram, Summary

# ==============================================================================
# INGESTION METRICS
# ==============================================================================

ingestion_records_total = Counter(
    "dataplatform_ingestion_records_total",
    "Total number of records ingested",
    ["source", "layer", "status"],
)

ingestion_bytes_total = Counter(
    "dataplatform_ingestion_bytes_total",
    "Total bytes ingested",
    ["source", "layer"],
)

ingestion_duration_seconds = Histogram(
    "dataplatform_ingestion_duration_seconds",
    "Time spent ingesting data",
    ["source", "layer"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

ingestion_errors_total = Counter(
    "dataplatform_ingestion_errors_total",
    "Total number of ingestion errors",
    ["source", "error_type"],
)

# ==============================================================================
# KAFKA METRICS
# ==============================================================================

kafka_messages_produced_total = Counter(
    "dataplatform_kafka_messages_produced_total",
    "Total messages produced to Kafka",
    ["topic", "status"],
)

kafka_messages_consumed_total = Counter(
    "dataplatform_kafka_messages_consumed_total",
    "Total messages consumed from Kafka",
    ["topic", "group_id", "status"],
)

kafka_producer_errors_total = Counter(
    "dataplatform_kafka_producer_errors_total",
    "Total Kafka producer errors",
    ["topic", "error_type"],
)

kafka_consumer_errors_total = Counter(
    "dataplatform_kafka_consumer_errors_total",
    "Total Kafka consumer errors",
    ["group_id", "error_type"],
)

kafka_producer_latency_seconds = Histogram(
    "dataplatform_kafka_producer_latency_seconds",
    "Kafka producer message latency",
    ["topic"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5),
)

kafka_consumer_lag = Gauge(
    "dataplatform_kafka_consumer_lag",
    "Consumer lag in messages",
    ["topic", "partition", "group_id"],
)

kafka_admin_operations_total = Counter(
    "dataplatform_kafka_admin_operations_total",
    "Total Kafka admin operations",
    ["operation", "status"],
)

# ==============================================================================
# PROCESSING METRICS (FLINK)
# ==============================================================================

flink_records_in_total = Counter(
    "dataplatform_flink_records_in_total",
    "Total records consumed by Flink jobs",
    ["job_name", "operator"],
)

flink_records_out_total = Counter(
    "dataplatform_flink_records_out_total",
    "Total records produced by Flink jobs",
    ["job_name", "operator"],
)

flink_processing_latency_ms = Histogram(
    "dataplatform_flink_processing_latency_ms",
    "Flink processing latency in milliseconds",
    ["job_name", "operator"],
    buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)

flink_checkpoint_duration_ms = Histogram(
    "dataplatform_flink_checkpoint_duration_ms",
    "Flink checkpoint duration in milliseconds",
    ["job_name"],
    buckets=(100, 500, 1000, 5000, 10000, 30000, 60000),
)

flink_job_status = Gauge(
    "dataplatform_flink_job_status",
    "Flink job status (1=running, 0=stopped)",
    ["job_name"],
)

# ==============================================================================
# STORAGE METRICS (ICEBERG/PAIMON)
# ==============================================================================

storage_table_size_bytes = Gauge(
    "dataplatform_storage_table_size_bytes",
    "Table size in bytes",
    ["layer", "namespace", "table"],
)

storage_table_files_count = Gauge(
    "dataplatform_storage_table_files_count",
    "Number of data files in table",
    ["layer", "namespace", "table"],
)

storage_table_rows_count = Gauge(
    "dataplatform_storage_table_rows_count",
    "Number of rows in table",
    ["layer", "namespace", "table"],
)

storage_snapshot_count = Gauge(
    "dataplatform_storage_snapshot_count",
    "Number of snapshots for table",
    ["layer", "namespace", "table"],
)

storage_write_duration_seconds = Histogram(
    "dataplatform_storage_write_duration_seconds",
    "Time spent writing to storage",
    ["layer", "operation"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

storage_read_duration_seconds = Histogram(
    "dataplatform_storage_read_duration_seconds",
    "Time spent reading from storage",
    ["layer", "operation"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
)

# ==============================================================================
# QUERY METRICS
# ==============================================================================

query_execution_total = Counter(
    "dataplatform_query_execution_total",
    "Total number of queries executed",
    ["engine", "status"],
)

query_duration_seconds = Histogram(
    "dataplatform_query_duration_seconds",
    "Query execution time",
    ["engine", "query_type"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

query_rows_scanned = Summary(
    "dataplatform_query_rows_scanned",
    "Number of rows scanned by queries",
    ["engine"],
)

query_bytes_scanned = Summary(
    "dataplatform_query_bytes_scanned",
    "Number of bytes scanned by queries",
    ["engine"],
)

query_cache_hit_total = Counter(
    "dataplatform_query_cache_hit_total",
    "Total query cache hits",
    ["engine"],
)

query_cache_miss_total = Counter(
    "dataplatform_query_cache_miss_total",
    "Total query cache misses",
    ["engine"],
)

# ==============================================================================
# VECTOR DATABASE METRICS
# ==============================================================================

vector_index_size = Gauge(
    "dataplatform_vector_index_size",
    "Number of vectors in index",
    ["database", "collection"],
)

vector_search_duration_ms = Histogram(
    "dataplatform_vector_search_duration_ms",
    "Vector search latency",
    ["database", "collection"],
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2500),
)

vector_insert_total = Counter(
    "dataplatform_vector_insert_total",
    "Total vectors inserted",
    ["database", "collection"],
)

vector_search_total = Counter(
    "dataplatform_vector_search_total",
    "Total vector searches",
    ["database", "collection", "search_type"],
)

# ==============================================================================
# DATA QUALITY METRICS
# ==============================================================================

data_quality_checks_total = Counter(
    "dataplatform_data_quality_checks_total",
    "Total data quality checks executed",
    ["layer", "table", "status"],
)

data_quality_failures_total = Counter(
    "dataplatform_data_quality_failures_total",
    "Total data quality check failures",
    ["layer", "table", "check_type"],
)

data_quality_score = Gauge(
    "dataplatform_data_quality_score",
    "Data quality score (0-100)",
    ["layer", "table"],
)

# ==============================================================================
# LINEAGE METRICS
# ==============================================================================

lineage_events_emitted_total = Counter(
    "dataplatform_lineage_events_emitted_total",
    "Total lineage events emitted",
    ["event_type"],
)

lineage_graph_nodes = Gauge(
    "dataplatform_lineage_graph_nodes",
    "Number of nodes in lineage graph",
    ["node_type"],
)

lineage_graph_edges = Gauge(
    "dataplatform_lineage_graph_edges",
    "Number of edges in lineage graph",
)

# ==============================================================================
# MCP SERVER METRICS
# ==============================================================================

mcp_requests_total = Counter(
    "dataplatform_mcp_requests_total",
    "Total MCP requests",
    ["server", "method", "status"],
)

mcp_request_duration_seconds = Histogram(
    "dataplatform_mcp_request_duration_seconds",
    "MCP request duration",
    ["server", "method"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10),
)

mcp_active_connections = Gauge(
    "dataplatform_mcp_active_connections",
    "Number of active MCP connections",
    ["server"],
)

# ==============================================================================
# AGENT METRICS
# ==============================================================================

agent_executions_total = Counter(
    "dataplatform_agent_executions_total",
    "Total agent executions",
    ["agent_type", "status"],
)

agent_execution_duration_seconds = Histogram(
    "dataplatform_agent_execution_duration_seconds",
    "Agent execution duration",
    ["agent_type"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600),
)

agent_tool_calls_total = Counter(
    "dataplatform_agent_tool_calls_total",
    "Total agent tool calls",
    ["agent_type", "tool_name"],
)

# ==============================================================================
# API METRICS
# ==============================================================================

api_requests_total = Counter(
    "dataplatform_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)

api_request_duration_seconds = Histogram(
    "dataplatform_api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5),
)

api_active_requests = Gauge(
    "dataplatform_api_active_requests",
    "Number of active API requests",
)

# ==============================================================================
# SYSTEM METRICS
# ==============================================================================

system_health_status = Gauge(
    "dataplatform_system_health_status",
    "Overall system health status (1=healthy, 0=unhealthy)",
    ["component"],
)

system_errors_total = Counter(
    "dataplatform_system_errors_total",
    "Total system errors",
    ["component", "error_type"],
)


# ==============================================================================
# DECORATOR UTILITIES
# ==============================================================================


def track_duration(metric: Histogram, labels: Optional[dict] = None):
    """
    Decorator to track function execution duration.

    Args:
        metric: Prometheus Histogram metric
        labels: Labels to apply to the metric

    Example:
        @track_duration(query_duration_seconds, {"engine": "trino"})
        def execute_query(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            labels_dict = labels or {}
            start_time = time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time() - start_time
                metric.labels(**labels_dict).observe(duration)

        return wrapper

    return decorator


def count_calls(metric: Counter, labels: Optional[dict] = None, status_arg: str = None):
    """
    Decorator to count function calls and track success/failure.

    Args:
        metric: Prometheus Counter metric
        labels: Labels to apply to the metric
        status_arg: If provided, use this argument as status label

    Example:
        @count_calls(ingestion_records_total, {"source": "api", "layer": "bronze"})
        def ingest_data(...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            labels_dict = labels or {}
            try:
                result = func(*args, **kwargs)
                labels_dict["status"] = "success"
                metric.labels(**labels_dict).inc()
                return result
            except Exception as e:
                labels_dict["status"] = "failure"
                metric.labels(**labels_dict).inc()
                raise

        return wrapper

    return decorator
