"""
Configuration Management

Centralized configuration management using Pydantic Settings.
Supports environment variables, .env files, and configuration files.
"""

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class DeploymentTarget(str, Enum):
    """Deployment target."""

    LOCAL = "local"
    AWS = "aws"
    KUBERNETES = "kubernetes"
    VM = "vm"


class StorageType(str, Enum):
    """Storage backend type."""

    MINIO = "minio"
    S3 = "s3"


class IcebergCatalogType(str, Enum):
    """Iceberg catalog type."""

    REST = "rest"
    GLUE = "glue"
    HIVE = "hive"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables and .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # ==========================================================================
    # ENVIRONMENT
    # ==========================================================================
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    log_level: str = Field(default="INFO")
    debug: bool = Field(default=False)

    # ==========================================================================
    # STORAGE CONFIGURATION
    # ==========================================================================
    storage_type: StorageType = Field(default=StorageType.MINIO)
    storage_endpoint: str = Field(default="http://localhost:9000")
    storage_access_key: str = Field(default="minioadmin")
    storage_secret_key: str = Field(default="minioadmin")
    storage_bucket_bronze: str = Field(default="lakehouse-bronze")
    storage_bucket_silver: str = Field(default="lakehouse-silver")
    storage_bucket_gold: str = Field(default="lakehouse-gold")
    storage_region: str = Field(default="us-east-1")

    # AWS S3
    aws_access_key_id: Optional[str] = Field(default=None)
    aws_secret_access_key: Optional[str] = Field(default=None)
    aws_region: str = Field(default="us-east-1")
    aws_s3_bucket_bronze: Optional[str] = Field(default=None)
    aws_s3_bucket_silver: Optional[str] = Field(default=None)
    aws_s3_bucket_gold: Optional[str] = Field(default=None)

    # ==========================================================================
    # APACHE ICEBERG
    # ==========================================================================
    iceberg_catalog_type: IcebergCatalogType = Field(default=IcebergCatalogType.REST)
    iceberg_catalog_uri: str = Field(default="http://localhost:8181")
    iceberg_warehouse_location: str = Field(default="s3://lakehouse/warehouse")
    iceberg_glue_catalog_id: Optional[str] = Field(default=None)
    iceberg_glue_region: str = Field(default="us-east-1")

    # ==========================================================================
    # APACHE PAIMON
    # ==========================================================================
    paimon_catalog_type: str = Field(default="filesystem")
    paimon_warehouse_path: str = Field(default="s3://lakehouse/paimon-warehouse")
    paimon_metastore_uri: Optional[str] = Field(default=None)

    # ==========================================================================
    # KAFKA
    # ==========================================================================
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092,localhost:9093,localhost:9094"
    )
    kafka_schema_registry_url: str = Field(default="http://localhost:8081")
    kafka_security_protocol: str = Field(default="PLAINTEXT")
    kafka_sasl_mechanism: Optional[str] = Field(default=None)
    kafka_sasl_username: Optional[str] = Field(default=None)
    kafka_sasl_password: Optional[str] = Field(default=None)

    # Kafka Topics
    kafka_topic_raw_events: str = Field(default="raw-events")
    kafka_topic_cdc_streams: str = Field(default="cdc-streams")
    kafka_topic_api_events: str = Field(default="api-events")
    kafka_topic_mcp_requests: str = Field(default="mcp-requests")
    kafka_topic_dlq: str = Field(default="dead-letter-queue")

    # ==========================================================================
    # APACHE FLINK
    # ==========================================================================
    flink_jobmanager_rpc_address: str = Field(default="localhost")
    flink_jobmanager_rpc_port: int = Field(default=6123)
    flink_rest_address: str = Field(default="localhost")
    flink_rest_port: int = Field(default=8081)
    flink_parallelism: int = Field(default=4)
    flink_checkpoint_interval: int = Field(default=60000)
    flink_checkpoint_dir: str = Field(default="s3://lakehouse/flink-checkpoints")

    # ==========================================================================
    # DATABASE (PostgreSQL)
    # ==========================================================================
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="dataplatform_metadata")
    postgres_user: str = Field(default="dataplatform")
    postgres_password: str = Field(default="dataplatform_password")
    postgres_schema: str = Field(default="public")
    db_pool_size: int = Field(default=20)
    db_max_overflow: int = Field(default=10)

    # ==========================================================================
    # VECTOR DATABASES
    # ==========================================================================
    # Pinecone
    pinecone_api_key: Optional[str] = Field(default=None)
    pinecone_environment: Optional[str] = Field(default=None)
    pinecone_index_name: str = Field(default="data-platform-vectors")

    # Milvus
    milvus_host: str = Field(default="localhost")
    milvus_port: int = Field(default=19530)
    milvus_user: Optional[str] = Field(default=None)
    milvus_password: Optional[str] = Field(default=None)
    milvus_db_name: str = Field(default="dataplatform")

    # Qdrant
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_api_key: Optional[str] = Field(default=None)
    qdrant_collection_name: str = Field(default="data-platform-vectors")

    # Embedding
    embedding_provider: str = Field(default="openai")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimension: int = Field(default=1536)

    # ==========================================================================
    # QUERY ENGINES
    # ==========================================================================
    # Trino
    trino_host: str = Field(default="localhost")
    trino_port: int = Field(default=8080)
    trino_user: str = Field(default="trino")
    trino_catalog: str = Field(default="iceberg")
    trino_schema: str = Field(default="default")

    # Spark
    spark_master: str = Field(default="local[*]")
    spark_app_name: str = Field(default="DataPlatform")
    spark_driver_memory: str = Field(default="4g")
    spark_executor_memory: str = Field(default="4g")

    # ==========================================================================
    # DATA CATALOG & GOVERNANCE
    # ==========================================================================
    datahub_gms_url: str = Field(default="http://localhost:8080")
    datahub_frontend_url: str = Field(default="http://localhost:9002")
    datahub_kafka_bootstrap: str = Field(default="localhost:9092")

    openlineage_url: str = Field(default="http://localhost:5000")
    openlineage_namespace: str = Field(default="dataplatform")
    openlineage_api_key: Optional[str] = Field(default=None)

    ge_checkpoint_store_path: str = Field(default="s3://lakehouse/ge-checkpoints")
    ge_validation_results_path: str = Field(default="s3://lakehouse/ge-validation-results")

    # ==========================================================================
    # SECURITY
    # ==========================================================================
    jwt_secret_key: str = Field(default="your-secret-key-change-this-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expiration_minutes: int = Field(default=60)

    oauth_enabled: bool = Field(default=False)
    oauth_provider: Optional[str] = Field(default=None)
    oauth_client_id: Optional[str] = Field(default=None)
    oauth_client_secret: Optional[str] = Field(default=None)

    opa_url: str = Field(default="http://localhost:8181")
    opa_policy_path: str = Field(default="/v1/data/dataplatform/allow")

    encryption_key: str = Field(default="your-encryption-key-change-this-in-production")
    encryption_algorithm: str = Field(default="AES256")

    # ==========================================================================
    # AI & LLM
    # ==========================================================================
    openai_api_key: Optional[str] = Field(default=None)
    openai_model: str = Field(default="gpt-4-turbo-preview")
    openai_max_tokens: int = Field(default=4096)

    cohere_api_key: Optional[str] = Field(default=None)

    local_llm_endpoint: Optional[str] = Field(default=None)
    local_llm_model: Optional[str] = Field(default=None)

    # ==========================================================================
    # MCP (MODEL CONTEXT PROTOCOL)
    # ==========================================================================
    mcp_server_host: str = Field(default="0.0.0.0")
    mcp_server_port: int = Field(default=8000)
    mcp_data_server_port: int = Field(default=8001)
    mcp_metadata_server_port: int = Field(default=8002)
    mcp_query_server_port: int = Field(default=8003)
    mcp_lineage_server_port: int = Field(default=8004)

    # ==========================================================================
    # API
    # ==========================================================================
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_workers: int = Field(default=4)
    api_reload: bool = Field(default=True)
    api_cors_origins: str = Field(default="*")

    api_rate_limit_enabled: bool = Field(default=True)
    api_rate_limit_per_minute: int = Field(default=100)

    # ==========================================================================
    # MONITORING
    # ==========================================================================
    prometheus_port: int = Field(default=9090)
    prometheus_scrape_interval: str = Field(default="15s")

    grafana_port: int = Field(default=3000)
    grafana_admin_user: str = Field(default="admin")
    grafana_admin_password: str = Field(default="admin")

    otel_enabled: bool = Field(default=True)
    otel_service_name: str = Field(default="data-platform")
    otel_exporter_otlp_endpoint: str = Field(default="http://localhost:4317")

    jaeger_agent_host: str = Field(default="localhost")
    jaeger_agent_port: int = Field(default=6831)

    # ==========================================================================
    # REDIS
    # ==========================================================================
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: Optional[str] = Field(default=None)
    redis_db: int = Field(default=0)
    redis_cache_ttl: int = Field(default=3600)

    # ==========================================================================
    # DEPLOYMENT
    # ==========================================================================
    deployment_target: DeploymentTarget = Field(default=DeploymentTarget.LOCAL)
    kubernetes_namespace: str = Field(default="dataplatform")
    aws_account_id: Optional[str] = Field(default=None)
    aws_eks_cluster_name: Optional[str] = Field(default=None)

    # ==========================================================================
    # FEATURE FLAGS
    # ==========================================================================
    feature_paimon_enabled: bool = Field(default=True)
    feature_vector_search_enabled: bool = Field(default=True)
    feature_mcp_enabled: bool = Field(default=True)
    feature_datahub_enabled: bool = Field(default=True)
    feature_openlineage_enabled: bool = Field(default=True)
    feature_data_quality_enabled: bool = Field(default=True)
    feature_agents_enabled: bool = Field(default=True)

    # ==========================================================================
    # DATA QUALITY & COMPLIANCE
    # ==========================================================================
    data_quality_check_enabled: bool = Field(default=True)
    pii_detection_enabled: bool = Field(default=True)
    gdpr_compliance_enabled: bool = Field(default=False)
    soc2_compliance_enabled: bool = Field(default=False)
    data_retention_days_bronze: int = Field(default=90)
    data_retention_days_silver: int = Field(default=730)
    data_retention_days_gold: int = Field(default=2555)

    # ==========================================================================
    # DEVELOPMENT & DEBUGGING
    # ==========================================================================
    enable_sql_echo: bool = Field(default=False)
    enable_profiling: bool = Field(default=False)
    mock_external_services: bool = Field(default=False)
    sample_data_generation: bool = Field(default=True)

    @field_validator("kafka_bootstrap_servers")
    @classmethod
    def validate_kafka_servers(cls, v: str) -> List[str]:
        """Validate and convert Kafka bootstrap servers to list."""
        return [server.strip() for server in v.split(",")]

    @field_validator("api_cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: str) -> List[str]:
        """Validate and convert CORS origins to list."""
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",")]

    @property
    def database_url(self) -> str:
        """Get PostgreSQL database URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT

    def get_storage_endpoint(self) -> str:
        """Get appropriate storage endpoint based on storage type."""
        if self.storage_type == StorageType.S3:
            return f"https://s3.{self.aws_region}.amazonaws.com"
        return self.storage_endpoint

    def get_bucket_name(self, layer: str) -> str:
        """Get bucket name for a specific layer."""
        if self.storage_type == StorageType.S3:
            bucket_map = {
                "bronze": self.aws_s3_bucket_bronze,
                "silver": self.aws_s3_bucket_silver,
                "gold": self.aws_s3_bucket_gold,
            }
        else:
            bucket_map = {
                "bronze": self.storage_bucket_bronze,
                "silver": self.storage_bucket_silver,
                "gold": self.storage_bucket_gold,
            }

        bucket = bucket_map.get(layer.lower())
        if not bucket:
            raise ValueError(f"Invalid layer: {layer}. Must be bronze, silver, or gold.")
        return bucket

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return self.model_dump()


@lru_cache()
def get_config() -> Settings:
    """
    Get cached configuration instance.

    Returns:
        Settings: Application settings
    """
    return Settings()


# Global settings instance
settings = get_config()
