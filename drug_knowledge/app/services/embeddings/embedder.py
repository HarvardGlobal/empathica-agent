from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

BATCH_SIZE = 32


class BaseEmbedder(ABC):
    """Abstract interface for text embedding."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Returns a list of embedding vectors."""

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""


class SentenceTransformerEmbedder(BaseEmbedder):
    """
    Sentence-Transformers based embedder.

    Lazy-loads the model on first call to avoid slow import at startup.
    Uses batch_size=32 for encoding.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: Optional[object] = None

    def _get_model(self) -> object:
        if self._model is None:
            logger.info("Loading SentenceTransformer model: %s", self._model_name)
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self._model_name)
            logger.info("Model loaded.")
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of texts in batches of 32.
        Returns a list of float vectors, one per input text.
        """
        if not texts:
            return []

        model = self._get_model()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            embeddings = model.encode(batch, batch_size=BATCH_SIZE, convert_to_numpy=True)  # type: ignore[attr-defined]
            all_embeddings.extend(embedding.tolist() for embedding in embeddings)

        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string."""
        model = self._get_model()
        embedding = model.encode([query], batch_size=1, convert_to_numpy=True)  # type: ignore[attr-defined]
        return embedding[0].tolist()
