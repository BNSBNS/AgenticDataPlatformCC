"""
Unit tests for Pinecone vector store.

Tests the PineconeVectorStore class including initialization,
index creation, upsert, search, and error handling.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class TestPineconeAvailability:
    """Test suite for Pinecone availability checks."""

    def test_pinecone_not_available_raises_import_error(self):
        """Test that ImportError is raised when pinecone not installed."""
        with patch.dict("sys.modules", {"pinecone": None}):
            with patch(
                "src.vector.stores.pinecone_store.PINECONE_AVAILABLE", False
            ):
                from src.vector.stores.pinecone_store import PineconeVectorStore

                with pytest.raises(ImportError, match="Pinecone client not installed"):
                    PineconeVectorStore(api_key="test-key")


class TestPineconeVectorStoreInit:
    """Test suite for PineconeVectorStore initialization."""

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_initialization_with_api_key(self, mock_config, mock_pinecone):
        """Test successful initialization with provided API key."""
        mock_config.return_value.pinecone_api_key = None
        mock_config.return_value.pinecone_index_name = "test-index"

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore(api_key="test-key")

        assert store.api_key == "test-key"
        mock_pinecone.assert_called_once_with(api_key="test-key")

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_initialization_with_config_api_key(self, mock_config, mock_pinecone):
        """Test initialization with API key from config."""
        mock_config.return_value.pinecone_api_key = "config-api-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()

        assert store.api_key == "config-api-key"
        mock_pinecone.assert_called_once_with(api_key="config-api-key")

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_initialization_without_api_key_raises_error(self, mock_config):
        """Test that missing API key raises VectorDatabaseError."""
        mock_config.return_value.pinecone_api_key = None
        mock_config.return_value.pinecone_index_name = "test-index"

        from src.vector.stores.pinecone_store import PineconeVectorStore
        from src.common.exceptions import VectorDatabaseError

        with pytest.raises(VectorDatabaseError, match="API key not configured"):
            PineconeVectorStore()


class TestPineconeVectorStoreCreateIndex:
    """Test suite for index creation."""

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.ServerlessSpec")
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_create_index_success(
        self, mock_config, mock_pinecone, mock_serverless_spec
    ):
        """Test successful index creation."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_client = MagicMock()
        mock_client.list_indexes.return_value = []
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        store.create_index("new-index", dimension=1536, metric="cosine")

        mock_client.create_index.assert_called_once()
        call_kwargs = mock_client.create_index.call_args
        assert call_kwargs.kwargs["name"] == "new-index"
        assert call_kwargs.kwargs["dimension"] == 1536
        assert call_kwargs.kwargs["metric"] == "cosine"

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_create_index_already_exists(self, mock_config, mock_pinecone):
        """Test that existing index is not recreated."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_index_info = MagicMock()
        mock_index_info.name = "existing-index"
        mock_client = MagicMock()
        mock_client.list_indexes.return_value = [mock_index_info]
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        store.create_index("existing-index")

        mock_client.create_index.assert_not_called()


class TestPineconeVectorStoreUpsert:
    """Test suite for vector upsert operations."""

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.vector_insert_total")
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_upsert_success(self, mock_config, mock_pinecone, mock_metric):
        """Test successful vector upsert."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        payloads = [{"text": "doc1"}, {"text": "doc2"}]
        ids = ["id1", "id2"]

        store.upsert("test-index", vectors, payloads, ids)

        mock_index.upsert.assert_called_once()
        mock_metric.labels.assert_called_with(database="pinecone", collection="test-index")

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.vector_insert_total")
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_upsert_generates_ids(self, mock_config, mock_pinecone, mock_metric):
        """Test that IDs are generated when not provided."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        vectors = [[0.1, 0.2, 0.3]]
        payloads = [{"text": "doc1"}]

        store.upsert("test-index", vectors, payloads)

        # Verify upsert was called with generated ID
        mock_index.upsert.assert_called_once()
        call_args = mock_index.upsert.call_args
        upserted_vectors = call_args.kwargs["vectors"]
        assert len(upserted_vectors) == 1
        assert "id" in upserted_vectors[0]

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.vector_insert_total")
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_upsert_batching(self, mock_config, mock_pinecone, mock_metric):
        """Test that large upserts are batched correctly."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()

        # Create 250 vectors (should require 3 batches with batch_size=100)
        vectors = [[0.1] * 3 for _ in range(250)]
        payloads = [{"text": f"doc{i}"} for i in range(250)]

        store.upsert("test-index", vectors, payloads, batch_size=100)

        # Should be called 3 times (100 + 100 + 50)
        assert mock_index.upsert.call_count == 3


class TestPineconeVectorStoreSearch:
    """Test suite for vector search operations."""

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.vector_search_total")
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_search_returns_correct_format(
        self, mock_config, mock_pinecone, mock_metric
    ):
        """Test search results match expected format."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        # Create mock search results
        mock_match = MagicMock()
        mock_match.id = "id1"
        mock_match.score = 0.95
        mock_match.metadata = {"text": "doc1"}

        mock_results = MagicMock()
        mock_results.matches = [mock_match]

        mock_index = MagicMock()
        mock_index.query.return_value = mock_results

        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        results = store.search("test-index", [0.1, 0.2, 0.3])

        assert len(results) == 1
        assert results[0]["id"] == "id1"
        assert results[0]["score"] == 0.95
        assert results[0]["payload"] == {"text": "doc1"}

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.vector_search_total")
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_search_with_filter(self, mock_config, mock_pinecone, mock_metric):
        """Test search with metadata filtering."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_results = MagicMock()
        mock_results.matches = []

        mock_index = MagicMock()
        mock_index.query.return_value = mock_results

        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        filter_dict = {"category": {"$eq": "tech"}}
        store.search("test-index", [0.1, 0.2, 0.3], filter=filter_dict)

        mock_index.query.assert_called_once()
        call_kwargs = mock_index.query.call_args.kwargs
        assert call_kwargs["filter"] == filter_dict


class TestPineconeVectorStoreErrorHandling:
    """Test suite for error handling."""

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_upsert_error_raises_vector_database_error(
        self, mock_config, mock_pinecone
    ):
        """Test that upsert errors raise VectorDatabaseError."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_index = MagicMock()
        mock_index.upsert.side_effect = Exception("Connection failed")

        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore
        from src.common.exceptions import VectorDatabaseError

        store = PineconeVectorStore()

        with pytest.raises(VectorDatabaseError, match="Upsert failed"):
            store.upsert("test-index", [[0.1]], [{"text": "doc"}])

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_search_error_raises_vector_database_error(
        self, mock_config, mock_pinecone
    ):
        """Test that search errors raise VectorDatabaseError."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_index = MagicMock()
        mock_index.query.side_effect = Exception("Query failed")

        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore
        from src.common.exceptions import VectorDatabaseError

        store = PineconeVectorStore()

        with pytest.raises(VectorDatabaseError, match="Search failed"):
            store.search("test-index", [0.1, 0.2, 0.3])


class TestPineconeVectorStoreUtilities:
    """Test suite for utility methods."""

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_list_indexes(self, mock_config, mock_pinecone):
        """Test listing indexes."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_idx1 = MagicMock()
        mock_idx1.name = "index1"
        mock_idx2 = MagicMock()
        mock_idx2.name = "index2"

        mock_client = MagicMock()
        mock_client.list_indexes.return_value = [mock_idx1, mock_idx2]
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        indexes = store.list_indexes()

        assert indexes == ["index1", "index2"]

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_describe_index(self, mock_config, mock_pinecone):
        """Test describing an index."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_stats = MagicMock()
        mock_stats.dimension = 1536
        mock_stats.total_vector_count = 1000
        mock_stats.namespaces = {"default": MagicMock()}

        mock_index = MagicMock()
        mock_index.describe_index_stats.return_value = mock_stats

        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        description = store.describe_index("test-index")

        assert description["name"] == "test-index"
        assert description["dimension"] == 1536
        assert description["total_vector_count"] == 1000

    @patch("src.vector.stores.pinecone_store.PINECONE_AVAILABLE", True)
    @patch("src.vector.stores.pinecone_store.Pinecone")
    @patch("src.vector.stores.pinecone_store.get_config")
    def test_delete_vectors(self, mock_config, mock_pinecone):
        """Test deleting vectors."""
        mock_config.return_value.pinecone_api_key = "test-key"
        mock_config.return_value.pinecone_index_name = "test-index"

        mock_index = MagicMock()
        mock_client = MagicMock()
        mock_client.Index.return_value = mock_index
        mock_pinecone.return_value = mock_client

        from src.vector.stores.pinecone_store import PineconeVectorStore

        store = PineconeVectorStore()
        store.delete_vectors("test-index", ["id1", "id2"])

        mock_index.delete.assert_called_once_with(
            ids=["id1", "id2"], namespace=""
        )
