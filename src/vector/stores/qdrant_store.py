"""
Qdrant vector store for semantic search.
"""

from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import VectorDatabaseError
from src.common.metrics import vector_insert_total, vector_search_total

logger = get_logger(__name__)


class QdrantVectorStore:
    """
    Qdrant vector database client for semantic search.

    Provides vector storage and similarity search capabilities.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 6333,
        collection_name: str = "documents",
    ):
        """
        Initialize Qdrant vector store.

        Args:
            host: Qdrant host
            port: Qdrant port
            collection_name: Default collection name
        """
        self.config = get_config()
        self.host = host or "localhost"
        self.port = port
        self.collection_name = collection_name

        # Initialize client
        self.client = QdrantClient(host=self.host, port=self.port)

        logger.info(
            "Qdrant vector store initialized",
            host=self.host,
            collection=collection_name,
        )

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1536,
        distance: str = "Cosine",
    ):
        """
        Create a new collection.

        Args:
            collection_name: Collection name
            vector_size: Dimension of vectors
            distance: Distance metric (Cosine, Euclid, Dot)
        """
        try:
            distance_map = {
                "Cosine": Distance.COSINE,
                "Euclid": Distance.EUCLID,
                "Dot": Distance.DOT,
            }

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance_map.get(distance, Distance.COSINE),
                ),
            )

            logger.info(f"Created collection: {collection_name}")

        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise VectorDatabaseError(f"Collection creation failed: {e}")

    def insert(
        self,
        collection_name: str,
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ):
        """
        Insert vectors into collection.

        Args:
            collection_name: Target collection
            vectors: List of embedding vectors
            payloads: Metadata for each vector
            ids: Optional IDs for vectors
        """
        try:
            # Generate IDs if not provided
            if ids is None:
                import uuid
                ids = [str(uuid.uuid4()) for _ in vectors]

            # Create points
            points = [
                PointStruct(id=id_, vector=vector, payload=payload)
                for id_, vector, payload in zip(ids, vectors, payloads)
            ]

            # Insert
            self.client.upsert(collection_name=collection_name, points=points)

            # Record metrics
            vector_insert_total.labels(
                database="qdrant", collection=collection_name
            ).inc(len(vectors))

            logger.info(f"Inserted {len(vectors)} vectors into {collection_name}")

        except Exception as e:
            logger.error(f"Vector insertion failed: {e}")
            raise VectorDatabaseError(f"Insert failed: {e}")

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            collection_name: Collection to search
            query_vector: Query embedding
            limit: Maximum results
            score_threshold: Minimum similarity score

        Returns:
            List of search results with scores and payloads
        """
        try:
            results = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )

            # Record metrics
            vector_search_total.labels(
                database="qdrant",
                collection=collection_name,
                search_type="similarity",
            ).inc()

            logger.info(f"Search returned {len(results)} results")

            return [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload,
                }
                for result in results
            ]

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise VectorDatabaseError(f"Search failed: {e}")
