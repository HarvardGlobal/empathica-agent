from __future__ import annotations

import math
import os
import logging
from collections.abc import Iterable
from typing import Any

from .document_embedding import embed_text
from .document_rag_store import query_patient_chunks
from .patient_document_retrieval import build_patient_document_context
from .patient_document_selector import select_patient_document_needs

logger = logging.getLogger(__name__)


def _keyword_fallback_enabled() -> bool:
    return os.getenv("KEYWORD_FALLBACK_ENABLED", "true").lower() == "true"


def _document_rag_enabled() -> bool:
    return os.getenv("DOCUMENT_RAG_ENABLED", "true").lower() == "true"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    length = min(len(a), len(b))
    if length == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(length))
    norm_a = math.sqrt(sum(v * v for v in a[:length]))
    norm_b = math.sqrt(sum(v * v for v in b[:length]))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _summarize_snippets(snippets: Iterable[dict[str, Any]]) -> str:
    parts = []
    for snippet in snippets:
        text = str(snippet.get("chunk_text") or "").strip()
        if not text:
            continue
        parts.append(text[:350].strip())
    if not parts:
        return ""
    return " ".join(parts).strip()


def _fallback_keyword_package(patient_id: str, query: str, docs_prefix: str | None) -> dict[str, Any]:
    selection = select_patient_document_needs(query)
    keyword_context = build_patient_document_context(selection, docs_prefix=docs_prefix or f"patients/{patient_id}/")
    snippet_text = keyword_context.strip()
    no_match = not snippet_text or any(
        phrase in snippet_text
        for phrase in (
            "No patient-specific unstructured document context was selected",
            "No relevant patient-specific document snippets were found.",
        )
    )
    snippets = []
    if snippet_text and not no_match:
        snippets.append(
            {
                "chunk_id": "keyword_fallback",
                "document_id": None,
                "source_path": None,
                "file_name": None,
                "chunk_text": snippet_text,
                "score": 0.0,
            }
        )
    status = "available" if snippets else "unavailable"
    return {
        "status": status,
        "retrieval_method": "keyword_fallback",
        "patient_id": patient_id,
        "docs_prefix": docs_prefix or f"patients/{patient_id}/",
        "query": query,
        "snippets": snippets,
        "missing_document_context": [] if snippets else ["No relevant uploaded document snippet was found."],
        "warnings": ["Keyword fallback used for patient document retrieval."],
        "source_trace": [
            {
                "source": "keyword_fallback",
                "docs_prefix": docs_prefix or f"patients/{patient_id}/",
                "selection": selection,
            }
        ],
        "summary": snippet_text if snippets else "No relevant uploaded document snippet was found.",
    }


def retrieve_patient_document_context(
    *,
    patient_id: str,
    query: str,
    top_k: int = 5,
    docs_prefix: str | None = None,
) -> dict[str, Any]:
    pid = (patient_id or "").strip()
    if not pid:
        return {
            "status": "error",
            "retrieval_method": "none",
            "patient_id": "",
            "docs_prefix": docs_prefix or "",
            "query": query,
            "snippets": [],
            "missing_document_context": ["No patient_id was provided."],
            "warnings": ["Missing patient_id."],
            "source_trace": [],
        }

    if not _document_rag_enabled():
        logger.info(
            "document_rag_runtime_disabled patient_id=%s retrieval_method=none fallback_used=false",
            pid,
        )
        return {
            "status": "unavailable",
            "retrieval_method": "none",
            "patient_id": pid,
            "docs_prefix": docs_prefix or f"patients/{pid}/",
            "query": query,
            "snippets": [],
            "missing_document_context": ["Document RAG is disabled."],
            "warnings": ["Document RAG is disabled."],
            "source_trace": [],
            "summary": "Document RAG is disabled.",
        }

    try:
        chunks = [chunk for chunk in query_patient_chunks(pid) if str(chunk.get("patient_id") or "") == pid]
        logger.info(
            "document_rag_runtime_start patient_id=%s enabled=%s available_chunks=%d retrieval_method=firestore_vector",
            pid,
            _document_rag_enabled(),
            len(chunks),
        )
        if not chunks:
            logger.info(
                "document_rag_runtime_complete patient_id=%s retrieval_method=none snippets_returned=0 fallback_used=false warnings=0",
                pid,
            )
            return {
                "status": "unavailable",
                "retrieval_method": "none",
                "patient_id": pid,
                "docs_prefix": docs_prefix or f"patients/{pid}/",
                "query": query,
                "snippets": [],
                "missing_document_context": ["No indexed patient document chunks were found."],
                "warnings": [],
                "source_trace": [{"source": "firestore", "patient_id": pid, "chunk_count": 0}],
                "summary": "No indexed patient document chunks were found.",
            }

        query_embedding = embed_text(query or "")
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in chunks:
            embedding = chunk.get("embedding") or []
            if hasattr(embedding, "values"):
                embedding = list(getattr(embedding, "values"))
            elif not isinstance(embedding, list):
                if isinstance(embedding, tuple):
                    embedding = list(embedding)
                else:
                    continue
            score = _cosine_similarity(query_embedding, [float(v) for v in embedding])
            scored.append((score, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        top_matches = [item for item in scored[: max(1, int(top_k))] if item[0] > 0.0]
        if not top_matches:
            if _keyword_fallback_enabled():
                fallback = _fallback_keyword_package(pid, query, docs_prefix)
                fallback["source_trace"].append(
                    {
                        "source": "firestore_vector",
                        "patient_id": pid,
                        "chunk_count": len(chunks),
                        "reason": "No positive-scoring snippets were found.",
                    }
                )
                fallback["status"] = "partial" if fallback["snippets"] else "unavailable"
                logger.info(
                    "document_rag_runtime_complete patient_id=%s retrieval_method=%s snippets_returned=%d fallback_used=true warnings=%d",
                    pid,
                    fallback["retrieval_method"],
                    len(fallback["snippets"]),
                    len(fallback.get("warnings", []) or []),
                )
                return fallback
            logger.info(
                "document_rag_runtime_complete patient_id=%s retrieval_method=firestore_vector snippets_returned=0 fallback_used=false warnings=1",
                pid,
            )
            return {
                "status": "partial",
                "retrieval_method": "firestore_vector",
                "patient_id": pid,
                "docs_prefix": docs_prefix or f"patients/{pid}/",
                "query": query,
                "snippets": [],
                "missing_document_context": ["No relevant uploaded document snippet was found."],
                "warnings": ["No positive-scoring chunks were found."],
                "source_trace": [{"source": "firestore", "patient_id": pid, "chunk_count": len(chunks)}],
                "summary": "No relevant uploaded document snippet was found.",
            }

        snippets = [
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "source_path": chunk.get("source_path"),
                "file_name": chunk.get("file_name"),
                "chunk_text": chunk.get("chunk_text"),
                "score": round(float(score), 4),
            }
            for score, chunk in top_matches
            if str(chunk.get("chunk_text") or "").strip()
        ]
        if not snippets:
            raise ValueError("No snippets available after scoring.")
        summary = _summarize_snippets(snippets)
        logger.info(
            "document_rag_runtime_complete patient_id=%s retrieval_method=firestore_vector chunks_available=%d snippets_returned=%d fallback_used=false",
            pid,
            len(chunks),
            len(snippets),
        )
        return {
            "status": "available",
            "retrieval_method": "firestore_vector",
            "patient_id": pid,
            "docs_prefix": docs_prefix or f"patients/{pid}/",
            "query": query,
            "snippets": snippets,
            "missing_document_context": [],
            "warnings": [],
            "source_trace": [{"source": "firestore", "patient_id": pid, "chunk_count": len(chunks)}],
            "summary": summary,
        }
    except Exception as exc:
        if _keyword_fallback_enabled():
            fallback = _fallback_keyword_package(pid, query, docs_prefix)
            fallback["warnings"].append(f"Firestore retrieval fallback triggered: {type(exc).__name__}.")
            fallback["docs_prefix"] = docs_prefix or f"patients/{pid}/"
            fallback["source_trace"].append(
                {
                    "source": "firestore_vector",
                    "patient_id": pid,
                    "error": type(exc).__name__,
                }
            )
            logger.info(
                "document_rag_runtime_complete patient_id=%s retrieval_method=%s snippets_returned=%d fallback_used=true warnings=%d error=%s",
                pid,
                fallback["retrieval_method"],
                len(fallback["snippets"]),
                len(fallback.get("warnings", []) or []),
                type(exc).__name__,
            )
            return fallback
        logger.info(
            "document_rag_runtime_complete patient_id=%s retrieval_method=none snippets_returned=0 fallback_used=false error=%s",
            pid,
            type(exc).__name__,
        )
        return {
            "status": "error",
            "retrieval_method": "none",
            "patient_id": pid,
            "docs_prefix": docs_prefix or f"patients/{pid}/",
            "query": query,
            "snippets": [],
            "missing_document_context": ["Document retrieval failed."],
            "warnings": [f"Document retrieval failed: {type(exc).__name__}."],
            "source_trace": [{"source": "firestore_vector", "patient_id": pid, "error": type(exc).__name__}],
            "summary": "Document retrieval failed.",
        }
