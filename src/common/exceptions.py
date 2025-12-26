"""
Custom Exceptions

Hierarchical exception classes for the data platform.
"""


class DataPlatformError(Exception):
    """Base exception for all data platform errors."""

    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class ConfigurationError(DataPlatformError):
    """Raised when there's a configuration error."""

    pass


class IngestionError(DataPlatformError):
    """Raised when data ingestion fails."""

    pass


class ProcessingError(DataPlatformError):
    """Raised when data processing fails."""

    pass


class StorageError(DataPlatformError):
    """Raised when storage operations fail."""

    pass


class QueryError(DataPlatformError):
    """Raised when query execution fails."""

    pass


class CatalogError(DataPlatformError):
    """Raised when catalog operations fail."""

    pass


class SchemaError(DataPlatformError):
    """Raised when schema validation or evolution fails."""

    pass


class LineageError(DataPlatformError):
    """Raised when lineage tracking fails."""

    pass


class QualityError(DataPlatformError):
    """Raised when data quality checks fail."""

    pass


class SecurityError(DataPlatformError):
    """Raised when security or access control fails."""

    pass


class VectorDatabaseError(DataPlatformError):
    """Raised when vector database operations fail."""

    pass


class MCPError(DataPlatformError):
    """Raised when MCP server operations fail."""

    pass


class AgentError(DataPlatformError):
    """Raised when agent operations fail."""

    pass


class KafkaError(DataPlatformError):
    """Raised when Kafka operations fail."""

    pass


class KafkaAdminError(KafkaError):
    """Raised when Kafka admin operations fail."""

    pass


class KafkaProducerError(KafkaError):
    """Raised when Kafka producer operations fail."""

    pass


class KafkaConsumerError(KafkaError):
    """Raised when Kafka consumer operations fail."""

    pass


class FlinkError(DataPlatformError):
    """Raised when Flink job operations fail."""

    pass


class IcebergError(StorageError):
    """Raised when Iceberg operations fail."""

    pass


class PaimonError(StorageError):
    """Raised when Paimon operations fail."""

    pass


class AuthenticationError(SecurityError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(SecurityError):
    """Raised when authorization fails."""

    pass


class ValidationError(DataPlatformError):
    """Raised when data validation fails."""

    pass


class RetryableError(DataPlatformError):
    """Base class for errors that should trigger retry logic."""

    pass


class NonRetryableError(DataPlatformError):
    """Base class for errors that should not trigger retry logic."""

    pass


class CircuitBreakerOpenError(DataPlatformError):
    """Raised when circuit breaker is open and rejects calls."""

    pass


class TimeoutError(DataPlatformError):
    """Raised when an operation times out."""

    pass
