from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas.retrieval import RAGRequest, RetrievalResponse, RetrievalPassage
from app.services.embeddings.embedder import SentenceTransformerEmbedder
from app.services.embeddings.vector_index import ChromaVectorIndex
from app.services.interactions import InteractionService

router = APIRouter(tags=["retrieval"])

# Shared lazy-loaded embedder and vector index instances
_embedder: SentenceTransformerEmbedder | None = None
_vector_index: ChromaVectorIndex | None = None


def _get_embedder() -> SentenceTransformerEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformerEmbedder(model_name=settings.EMBEDDING_MODEL)
    return _embedder


def _get_vector_index() -> ChromaVectorIndex:
    global _vector_index
    if _vector_index is None:
        _vector_index = ChromaVectorIndex(persist_directory=settings.VECTOR_STORE_PATH)
    return _vector_index


def get_interaction_service(db: Session = Depends(get_db)) -> InteractionService:
    return InteractionService(db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/interactions")
def get_drug_interaction(
    drug_a_id: str,
    drug_b_id: str,
    svc: InteractionService = Depends(get_interaction_service),
) -> dict:
    """
    Retrieve the interaction record between two drugs.
    Lookup is order-insensitive.
    """
    return svc.get_interaction(drug_a_id, drug_b_id)


@router.post("/rag/retrieve", response_model=RetrievalResponse)
def rag_retrieve(request: RAGRequest) -> RetrievalResponse:
    """
    Perform semantic search over drug label chunks.
    Returns top_k passages ranked by embedding similarity.
    """
    embedder = _get_embedder()
    vector_index = _get_vector_index()

    try:
        query_embedding = embedder.embed_query(request.query)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {exc}") from exc

    try:
        raw_results = vector_index.search(
            query_embedding=query_embedding,
            drug_id=request.drug_id,
            section_types=request.section_types,
            top_k=request.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {exc}") from exc

    passages = [
        RetrievalPassage(
            chunk_id=r["chunk_id"],
            section_type=r["section_type"],
            chunk_text=r["chunk_text"],
            score=r["score"],
            source_url=r.get("source_url"),
        )
        for r in raw_results
    ]

    return RetrievalResponse(passages=passages, source_type="vector")
