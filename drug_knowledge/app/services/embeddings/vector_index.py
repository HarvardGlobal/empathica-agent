from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)

COLLECTION_NAME = "drug_label_chunks"


class BaseVectorIndex(ABC):
    """Abstract interface for a vector store."""

    @abstractmethod
    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """
        Add chunks to the index.
        Each dict must contain: chunk_id, drug_id, section_type, chunk_text, embedding.
        """

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        drug_id: str,
        section_types: list[str],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search the index.
        Filter by drug_id; optionally filter by section_types.
        Returns list of dicts with: chunk_id, section_type, chunk_text, score, source_url.
        """

    @abstractmethod
    def remove_by_drug_id(self, drug_id: str) -> None:
        """Remove all vectors associated with the given drug_id."""

    @abstractmethod
    def persist(self) -> None:
        """Persist any in-memory state to disk."""


class ChromaVectorIndex(BaseVectorIndex):
    """
    ChromaDB-backed vector index with drug_id and section_type filtering.
    Uses a single persistent collection for all drug label chunks.
    """

    def __init__(self, persist_directory: str) -> None:
        self._persist_directory = persist_directory
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None

    def _get_collection(self) -> Any:
        if self._collection is None:
            import chromadb  # type: ignore

            self._client = chromadb.PersistentClient(path=self._persist_directory)
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """
        Add or update chunks in the ChromaDB collection.

        Expected keys per chunk dict:
          chunk_id, drug_id, section_type, chunk_text, embedding,
          and optionally source_url.
        """
        if not chunks:
            return

        collection = self._get_collection()

        ids = [c["chunk_id"] for c in chunks]
        embeddings = [c["embedding"] for c in chunks]
        documents = [c["chunk_text"] for c in chunks]
        metadatas = [
            {
                "drug_id": c["drug_id"],
                "section_type": c["section_type"],
                "source_url": c.get("source_url", ""),
            }
            for c in chunks
        ]

        # ChromaDB upsert is idempotent on IDs
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.debug("Upserted %d chunks into ChromaDB.", len(chunks))

    def search(
        self,
        query_embedding: list[float],
        drug_id: str,
        section_types: list[str],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search for the top_k most similar chunks filtered by drug_id and section_types.
        """
        collection = self._get_collection()

        # Build where filter
        where: dict[str, Any] = {"drug_id": {"$eq": drug_id}}
        if section_types:
            where = {
                "$and": [
                    {"drug_id": {"$eq": drug_id}},
                    {"section_type": {"$in": section_types}},
                ]
            }

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.error("ChromaDB query failed: %s", exc)
            return []

        passages: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for chunk_id, doc, meta, dist in zip(ids, documents, metadatas, distances):
            # Convert cosine distance (0=identical, 2=opposite) to similarity score
            score = 1.0 - (float(dist) / 2.0)
            passages.append(
                {
                    "chunk_id": chunk_id,
                    "section_type": meta.get("section_type", ""),
                    "chunk_text": doc,
                    "score": score,
                    "source_url": meta.get("source_url") or None,
                }
            )

        return passages

    def remove_by_drug_id(self, drug_id: str) -> None:
        """Delete all vectors for the given drug_id."""
        collection = self._get_collection()
        try:
            collection.delete(where={"drug_id": {"$eq": drug_id}})
            logger.info("Removed all vectors for drug_id=%s", drug_id)
        except Exception as exc:
            logger.error("Failed to remove vectors for drug_id=%s: %s", drug_id, exc)

    def persist(self) -> None:
        """
        ChromaDB PersistentClient auto-persists, but this method is provided
        for explicit flush if needed.
        """
        logger.debug("ChromaDB persist called (auto-persisted by PersistentClient).")
