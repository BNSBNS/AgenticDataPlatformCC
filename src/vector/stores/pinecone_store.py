"""
Pinecone vector store for semantic search.
"""

from typing import List, Dict, Any, Optional

# Try to import Pinecone client - it's an optional dependency
try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False
    Pinecone = None
    ServerlessSpec = None

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import VectorDatabaseError
from src.common.metrics import vector_insert_total, vector_search_total

logger = get_logger(__name__)


class PineconeVectorStore:
    """
    Pinecone vector database client for semantic search.

    Provides vector storage and similarity search capabilities using
    Pinecone's managed vector database service.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
    ):
        """
        Initialize Pinecone vector store.

        Args:
            api_key: Pinecone API key (falls back to config)
            index_name: Default index name (falls back to config)

        Raises:
            ImportError: If Pinecone client is not installed
            VectorDatabaseError: If API key is not configured
        """
        if not PINECONE_AVAILABLE:
            raise ImportError(
                "Pinecone client not installed. Install with: pip install pinecone-client"
            )

        self.config = get_config()
        self.api_key = api_key or self.config.pinecone_api_key
        self.index_name = index_name or self.config.pinecone_index_name

        if not self.api_key:
            raise VectorDatabaseError(
                "Pinecone API key not configured. Set PINECONE_API_KEY environment variable."
            )

        # Initialize Pinecone client
        self.client = Pinecone(api_key=self.api_key)

        logger.info(
            "Pinecone vector store initialized",
            index=self.index_name,
        )

    def create_index(
        self,
        index_name: str,
        dimension: int = 1536,
        metric: str = "cosine",
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        """
        Create a new Pinecone index with serverless spec.

        Args:
            index_name: Name of the index
            dimension: Vector dimension (default 1536 for OpenAI embeddings)
            metric: Distance metric (cosine, euclidean, dotproduct)
            cloud: Cloud provider (aws, gcp, azure)
            region: Region for the index
        """
        try:
            # Check if index already exists
            existing_indexes = [idx.name for idx in self.client.list_indexes()]
            if index_name in existing_indexes:
                logger.info(f"Index {index_name} already exists")
                return

            self.client.create_index(
                name=index_name,
                dimension=dimension,
                metric=metric,
                spec=ServerlessSpec(cloud=cloud, region=region),
            )

            logger.info(
                f"Created index: {index_name}",
                dimension=dimension,
                metric=metric,
            )

        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise VectorDatabaseError(f"Index creation failed: {e}")

    def upsert(
        self,
        index_name: str,
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
        namespace: str = "",
        batch_size: int = 100,
    ) -> None:
        """
        Upsert vectors into index.

        Args:
            index_name: Target index
            vectors: List of embedding vectors
            payloads: Metadata for each vector
            ids: Optional IDs (generated if not provided)
            namespace: Pinecone namespace for partitioning
            batch_size: Batch size for upsert operations
        """
        try:
            # Generate IDs if not provided
            if ids is None:
                import uuid
                ids = [str(uuid.uuid4()) for _ in vectors]

            # Get index
            index = self.client.Index(index_name)

            # Format vectors as tuples: (id, values, metadata)
            records = [
                {"id": id_, "values": vector, "metadata": payload}
                for id_, vector, payload in zip(ids, vectors, payloads)
            ]

            # Batch upserts
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                index.upsert(vectors=batch, namespace=namespace)

            # Record metrics
            vector_insert_total.labels(
                database="pinecone", collection=index_name
            ).inc(len(vectors))

            logger.info(f"Upserted {len(vectors)} vectors into {index_name}")

        except Exception as e:
            logger.error(f"Vector upsert failed: {e}")
            raise VectorDatabaseError(f"Upsert failed: {e}")

    def search(
        self,
        index_name: str,
        query_vector: List[float],
        limit: int = 10,
        namespace: str = "",
        filter: Optional[Dict[str, Any]] = None,
        include_metadata: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            index_name: Index to search
            query_vector: Query embedding
            limit: Maximum results (top_k)
            namespace: Pinecone namespace
            filter: Metadata filter (Pinecone syntax: {"field": {"$eq": "value"}})
            include_metadata: Whether to return metadata

        Returns:
            List of search results with id, score, and payload
        """
        try:
            index = self.client.Index(index_name)

            results = index.query(
                vector=query_vector,
                top_k=limit,
                namespace=namespace,
                filter=filter,
                include_metadata=include_metadata,
            )

            # Record metrics
            vector_search_total.labels(
                database="pinecone",
                collection=index_name,
                search_type="similarity",
            ).inc()

            logger.info(f"Search returned {len(results.matches)} results")

            # Return normalized format matching Qdrant
            return [
                {
                    "id": match.id,
                    "score": match.score,
                    "payload": match.metadata or {},
                }
                for match in results.matches
            ]

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise VectorDatabaseError(f"Search failed: {e}")

    def delete_index(self, index_name: str) -> None:
        """
        Delete an index.

        Args:
            index_name: Name of the index to delete
        """
        try:
            self.client.delete_index(index_name)
            logger.info(f"Deleted index: {index_name}")

        except Exception as e:
            logger.error(f"Failed to delete index: {e}")
            raise VectorDatabaseError(f"Index deletion failed: {e}")

    def list_indexes(self) -> List[str]:
        """
        List all indexes.

        Returns:
            List of index names
        """
        try:
            indexes = self.client.list_indexes()
            return [idx.name for idx in indexes]

        except Exception as e:
            logger.error(f"Failed to list indexes: {e}")
            raise VectorDatabaseError(f"List indexes failed: {e}")

    def describe_index(self, index_name: str) -> Dict[str, Any]:
        """
        Get index statistics and configuration.

        Args:
            index_name: Name of the index

        Returns:
            Index description with stats
        """
        try:
            index = self.client.Index(index_name)
            stats = index.describe_index_stats()

            return {
                "name": index_name,
                "dimension": stats.dimension,
                "total_vector_count": stats.total_vector_count,
                "namespaces": dict(stats.namespaces) if stats.namespaces else {},
            }

        except Exception as e:
            logger.error(f"Failed to describe index: {e}")
            raise VectorDatabaseError(f"Describe index failed: {e}")

    def delete_vectors(
        self,
        index_name: str,
        ids: List[str],
        namespace: str = "",
    ) -> None:
        """
        Delete vectors by ID.

        Args:
            index_name: Target index
            ids: List of vector IDs to delete
            namespace: Pinecone namespace
        """
        try:
            index = self.client.Index(index_name)
            index.delete(ids=ids, namespace=namespace)

            logger.info(f"Deleted {len(ids)} vectors from {index_name}")

        except Exception as e:
            logger.error(f"Failed to delete vectors: {e}")
            raise VectorDatabaseError(f"Vector deletion failed: {e}")
