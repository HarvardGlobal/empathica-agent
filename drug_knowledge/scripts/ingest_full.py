#!/usr/bin/env python3
"""
CLI script: run full ingestion from DailyMed, then rebuild all embeddings.

Usage:
    python scripts/ingest_full.py [--limit N]
"""
from __future__ import annotations

import argparse
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
from app.services.ingestion.dailymed_client import DailyMedClient
from app.services.ingestion.loader import DBLoader
from app.services.ingestion.normalizer import LabelNormalizer
from app.services.ingestion.openfda_client import OpenFDAClient
from app.services.ingestion.parser import LabelParser
from app.services.ingestion.updater import IngestionUpdater

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full DailyMed ingestion + embed all chunks.")
    parser.add_argument("--limit", type=int, default=100, help="Max labels to ingest")
    args = parser.parse_args()

    logger.info("Initializing database...")
    init_db()

    db = SessionLocal()
    try:
        # ------------------------------------------------------------------
        # Step 1: Run full ingestion
        # ------------------------------------------------------------------
        logger.info("Starting full ingestion (limit=%d)...", args.limit)
        dailymed_client = DailyMedClient(base_url=settings.DAILYMED_BASE_URL)
        openfda_client = OpenFDAClient(
            base_url=settings.OPENFDA_BASE_URL,
            api_key=settings.OPENFDA_API_KEY,
        )
        label_parser = LabelParser()
        normalizer = LabelNormalizer()
        loader = DBLoader(db)
        updater = IngestionUpdater(
            db=db,
            dailymed_client=dailymed_client,
            openfda_client=openfda_client,
            parser=label_parser,
            normalizer=normalizer,
            loader=loader,
        )

        run = updater.run_full_ingest(limit=args.limit)
        logger.info(
            "Full ingest finished: status=%s inserted=%d updated=%d failed=%d",
            run.status,
            run.records_inserted,
            run.records_updated,
            run.records_failed,
        )

        # ------------------------------------------------------------------
        # Step 2: Rebuild embeddings
        # ------------------------------------------------------------------
        logger.info("Rebuilding embeddings for all chunks...")
        embedder = SentenceTransformerEmbedder(model_name=settings.EMBEDDING_MODEL)
        vector_index = ChromaVectorIndex(persist_directory=settings.VECTOR_STORE_PATH)

        chunks = db.query(DrugLabelChunk).all()
        logger.info("Total chunks to embed: %d", len(chunks))

        batch_size = 32
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            texts = [c.chunk_text for c in batch]
            embeddings = embedder.embed_texts(texts)
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

            if (i // batch_size + 1) % 10 == 0:
                logger.info("Embedded %d / %d chunks...", min(i + batch_size, len(chunks)), len(chunks))

        db.commit()
        vector_index.persist()
        logger.info("Embedding rebuild complete.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
