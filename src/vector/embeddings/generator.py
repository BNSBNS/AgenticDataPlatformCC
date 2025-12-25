"""
Embedding generation for vector search.
"""

from typing import List, Optional
import openai

from src.common.config import get_config
from src.common.logging import get_logger
from src.common.exceptions import ProcessingError

logger = get_logger(__name__)


class EmbeddingGenerator:
    """
    Generate embeddings for text using OpenAI or local models.
    """

    def __init__(self, model: str = "text-embedding-ada-002"):
        """
        Initialize embedding generator.

        Args:
            model: Embedding model to use
        """
        self.config = get_config()
        self.model = model

        logger.info("Embedding generator initialized", model=model)

    def generate(self, text: str) -> List[float]:
        """
        Generate embedding for single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        try:
            response = openai.Embedding.create(input=text, model=self.model)
            embedding = response["data"][0]["embedding"]

            logger.debug(f"Generated embedding of size {len(embedding)}")

            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise ProcessingError(f"Failed to generate embedding: {e}")

    def generate_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        try:
            response = openai.Embedding.create(input=texts, model=self.model)
            embeddings = [item["embedding"] for item in response["data"]]

            logger.info(f"Generated {len(embeddings)} embeddings")

            return embeddings

        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise ProcessingError(f"Failed to generate embeddings: {e}")
