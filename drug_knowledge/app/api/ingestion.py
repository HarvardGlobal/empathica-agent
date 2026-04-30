from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.drug import DrugLabelChunk
from app.schemas.drug import IngestionRunRead
from app.services.embeddings.embedder import SentenceTransformerEmbedder
from app.services.embeddings.vector_index import ChromaVectorIndex
from app.services.ingestion.dailymed_client import DailyMedClient
from app.services.ingestion.loader import DBLoader
from app.services.ingestion.normalizer import LabelNormalizer
from app.services.ingestion.openfda_client import OpenFDAClient
from app.services.ingestion.parser import LabelParser
from app.services.ingestion.updater import IngestionUpdater

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])


def _build_updater(db: Session) -> IngestionUpdater:
    dailymed_client = DailyMedClient(base_url=settings.DAILYMED_BASE_URL)
    openfda_client = OpenFDAClient(
        base_url=settings.OPENFDA_BASE_URL,
        api_key=settings.OPENFDA_API_KEY,
    )
    parser = LabelParser()
    normalizer = LabelNormalizer()
    loader = DBLoader(db)
    return IngestionUpdater(
        db=db,
        dailymed_client=dailymed_client,
        openfda_client=openfda_client,
        parser=parser,
        normalizer=normalizer,
        loader=loader,
    )


def _run_full_ingest_task(limit: int) -> None:
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        updater = _build_updater(db)
        run = updater.run_full_ingest(limit=limit)
        logger.info("Full ingest complete: %s", run.status)
    except Exception as exc:
        logger.error("Full ingest background task failed: %s", exc)
    finally:
        db.close()


def _run_incremental_task(days_back: int) -> None:
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        updater = _build_updater(db)
        run = updater.run_incremental_update(days_back=days_back)
        logger.info("Incremental update complete: %s", run.status)
    except Exception as exc:
        logger.error("Incremental update background task failed: %s", exc)
    finally:
        db.close()


def _rebuild_embeddings_task() -> None:
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        embedder = SentenceTransformerEmbedder(model_name=settings.EMBEDDING_MODEL)
        vector_index = ChromaVectorIndex(persist_directory=settings.VECTOR_STORE_PATH)

        chunks = db.query(DrugLabelChunk).all()
        logger.info("Rebuilding embeddings for %d chunks.", len(chunks))

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

            # Mark chunks with the embedding model used
            for chunk in batch:
                chunk.embedding_model = settings.EMBEDDING_MODEL

        db.commit()
        vector_index.persist()
        logger.info("Embeddings rebuild complete.")
    except Exception as exc:
        logger.error("Rebuild embeddings task failed: %s", exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/ingestion/full")
def trigger_full_ingest(
    background_tasks: BackgroundTasks,
    limit: int = 100,
) -> dict:
    """
    Trigger a full ingestion run from DailyMed in the background.
    Returns immediately; check ingestion_runs table for status.
    """
    background_tasks.add_task(_run_full_ingest_task, limit)
    return {"status": "accepted", "message": f"Full ingest started (limit={limit})"}


@router.post("/ingestion/update")
def trigger_incremental_update(
    background_tasks: BackgroundTasks,
    days_back: int = 7,
) -> dict:
    """
    Trigger an incremental update (labels from the last N days) in the background.
    """
    background_tasks.add_task(_run_incremental_task, days_back)
    return {
        "status": "accepted",
        "message": f"Incremental update started (days_back={days_back})",
    }


@router.post("/embeddings/rebuild")
def trigger_rebuild_embeddings(background_tasks: BackgroundTasks) -> dict:
    """
    Re-embed all DrugLabelChunks and rebuild the vector index in the background.
    """
    background_tasks.add_task(_rebuild_embeddings_task)
    return {"status": "accepted", "message": "Embedding rebuild started"}
