#!/usr/bin/env python3
"""
CLI script: re-embed all DrugLabelChunks and rebuild the vector index.

Usage:
    python scripts/rebuild_embeddings.py
"""
from __future__ import annotations

import logging
import sys
import os

# Make 'app' importable when running from the drug_knowledge/ directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.db import SessionLocal, init_db
from app.models.drug import DrugLabelChunk
from app.services.embeddings.embedder import SentenceTransformerEmbedder
from app.services.embeddings.vector_index import ChromaVectorIndex

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Initializing database...")
    init_db()

    db = SessionLocal()
    try:
        embedder = SentenceTransformerEmbedder(model_name=settings.EMBEDDING_MODEL)
        vector_index = ChromaVectorIndex(persist_directory=settings.VECTOR_STORE_PATH)

        chunks = db.query(DrugLabelChunk).all()
        total = len(chunks)
        logger.info("Total DrugLabelChunks to embed: %d", total)

        if total == 0:
            logger.info("No chunks found. Run ingestion first.")
            return

        batch_size = 32
        embedded_count = 0

        for i in range(0, total, batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.chunk_text for c in batch]

            try:
                embeddings = embedder.embed_texts(texts)
            except Exception as exc:
                logger.error("Embedding batch %d failed: %s", i // batch_size, exc)
                continue

            chunk_dicts = [
                {
                    "chunk_id": c.id,
                    "drug_id": c.drug_id,
                    "section_type": c.section_type,
                    "chunk_text": c.chunk_text,
                    "embedding": emb,
                    "source_url": c.source_url or "",
                }
                for c, emb in zip(batch, embeddings)
            ]

            vector_index.add_chunks(chunk_dicts)

            for chunk in batch:
                chunk.embedding_model = settings.EMBEDDING_MODEL

            embedded_count += len(batch)

            if embedded_count % (batch_size * 10) == 0 or embedded_count == total:
                logger.info("Embedded %d / %d chunks...", embedded_count, total)

        db.commit()
        vector_index.persist()
        logger.info("Embedding rebuild complete. Embedded %d chunks.", embedded_count)

    finally:
        db.close()


if __name__ == "__main__":
    main()
