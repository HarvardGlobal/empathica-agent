from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from typing import Iterable

VERTEX_AI_PROJECT = os.getenv("VERTEX_AI_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
VERTEX_AI_REGION = os.getenv("VERTEX_AI_REGION", os.getenv("GOOGLE_CLOUD_LOCATION", "us-east4"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "gemini-embedding-001")


def _allow_fake_embeddings() -> bool:
    return os.getenv("ALLOW_FAKE_EMBEDDINGS", "false").lower() == "true"


def _hash_embedding(text: str, dimensions: int = 768) -> list[float]:
    digest = hashlib.sha256((text or "").encode("utf-8")).digest()
    values: list[float] = []
    for idx in range(dimensions):
        byte = digest[idx % len(digest)]
        values.append((byte / 255.0) * 2.0 - 1.0)
    return values


@lru_cache(maxsize=1)
def _load_model():
    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel

        if VERTEX_AI_PROJECT:
            vertexai.init(project=VERTEX_AI_PROJECT, location=VERTEX_AI_REGION)
        return TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL_NAME)
    except Exception:
        return None


def embed_text(text: str) -> list[float]:
    model = _load_model()
    if model is None:
        if _allow_fake_embeddings():
            return _hash_embedding(text)
        raise RuntimeError("Vertex embedding model unavailable and ALLOW_FAKE_EMBEDDINGS is false.")

    try:
        embeddings = model.get_embeddings([text or ""], auto_truncate=True)
        if embeddings and getattr(embeddings[0], "values", None):
            return [float(value) for value in embeddings[0].values]
    except Exception:
        if _allow_fake_embeddings():
            return _hash_embedding(text)
        raise


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    return [embed_text(text) for text in texts]
