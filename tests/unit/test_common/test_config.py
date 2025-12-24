"""
Unit tests for configuration management.

Tests the configuration system including environment variables,
validation, and helper methods.
"""

import pytest
from pydantic import ValidationError

from src.common.config import Environment, Settings, get_config


class TestSettings:
    """Test suite for Settings class."""

    def test_default_settings(self):
        """Test that default settings are loaded correctly."""
        settings = Settings()

        assert settings.environment == Environment.DEVELOPMENT
        assert settings.log_level == "INFO"
        assert settings.storage_type.value == "minio"
        assert settings.kafka_bootstrap_servers == "localhost:9092,localhost:9093,localhost:9094"

    def test_environment_override(self, mock_env_vars):
        """Test that environment variables override defaults."""
        mock_env_vars.setenv("ENVIRONMENT", "production")
        mock_env_vars.setenv("LOG_LEVEL", "ERROR")
        mock_env_vars.setenv("DEBUG", "false")

        settings = Settings()

        assert settings.environment == Environment.PRODUCTION
        assert settings.log_level == "ERROR"
        assert settings.debug is False

    def test_database_url_property(self):
        """Test database URL construction."""
        settings = Settings(
            postgres_host="testhost",
            postgres_port=5433,
            postgres_user="testuser",
            postgres_password="testpass",
            postgres_db="testdb",
        )

        expected_url = "postgresql://testuser:testpass@testhost:5433/testdb"
        assert settings.database_url == expected_url

    def test_is_production_property(self):
        """Test is_production property."""
        dev_settings = Settings(environment=Environment.DEVELOPMENT)
        prod_settings = Settings(environment=Environment.PRODUCTION)

        assert dev_settings.is_production is False
        assert prod_settings.is_production is True

    def test_is_development_property(self):
        """Test is_development property."""
        dev_settings = Settings(environment=Environment.DEVELOPMENT)
        prod_settings = Settings(environment=Environment.PRODUCTION)

        assert dev_settings.is_development is True
        assert prod_settings.is_development is False

    def test_get_storage_endpoint_minio(self):
        """Test storage endpoint for MinIO."""
        settings = Settings(
            storage_type="minio", storage_endpoint="http://localhost:9000"
        )

        assert settings.get_storage_endpoint() == "http://localhost:9000"

    def test_get_storage_endpoint_s3(self):
        """Test storage endpoint for S3."""
        settings = Settings(storage_type="s3", aws_region="us-west-2")

        assert settings.get_storage_endpoint() == "https://s3.us-west-2.amazonaws.com"

    def test_get_bucket_name_bronze(self):
        """Test getting bucket name for bronze layer."""
        settings = Settings(storage_bucket_bronze="test-bronze")

        assert settings.get_bucket_name("bronze") == "test-bronze"
        assert settings.get_bucket_name("BRONZE") == "test-bronze"  # Case insensitive

    def test_get_bucket_name_silver(self):
        """Test getting bucket name for silver layer."""
        settings = Settings(storage_bucket_silver="test-silver")

        assert settings.get_bucket_name("silver") == "test-silver"

    def test_get_bucket_name_gold(self):
        """Test getting bucket name for gold layer."""
        settings = Settings(storage_bucket_gold="test-gold")

        assert settings.get_bucket_name("gold") == "test-gold"

    def test_get_bucket_name_invalid_layer(self):
        """Test that invalid layer raises ValueError."""
        settings = Settings()

        with pytest.raises(ValueError, match="Invalid layer"):
            settings.get_bucket_name("platinum")

    def test_kafka_bootstrap_servers_parsing(self):
        """Test that Kafka bootstrap servers are parsed correctly."""
        settings = Settings(
            kafka_bootstrap_servers="server1:9092,server2:9092,server3:9092"
        )

        servers = settings.kafka_bootstrap_servers
        assert isinstance(servers, list)
        assert len(servers) == 3
        assert "server1:9092" in servers
        assert "server2:9092" in servers
        assert "server3:9092" in servers

    def test_cors_origins_parsing_wildcard(self):
        """Test CORS origins parsing with wildcard."""
        settings = Settings(api_cors_origins="*")

        origins = settings.api_cors_origins
        assert isinstance(origins, list)
        assert origins == ["*"]

    def test_cors_origins_parsing_multiple(self):
        """Test CORS origins parsing with multiple origins."""
        settings = Settings(
            api_cors_origins="http://localhost:3000,https://example.com"
        )

        origins = settings.api_cors_origins
        assert isinstance(origins, list)
        assert len(origins) == 2
        assert "http://localhost:3000" in origins
        assert "https://example.com" in origins

    def test_to_dict(self):
        """Test conversion to dictionary."""
        settings = Settings()
        config_dict = settings.to_dict()

        assert isinstance(config_dict, dict)
        assert "environment" in config_dict
        assert "storage_type" in config_dict
        assert config_dict["environment"] == Environment.DEVELOPMENT


class TestGetConfig:
    """Test suite for get_config function."""

    def test_get_config_singleton(self):
        """Test that get_config returns singleton instance."""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_get_config_returns_settings(self):
        """Test that get_config returns Settings instance."""
        config = get_config()

        assert isinstance(config, Settings)
