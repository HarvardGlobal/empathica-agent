from __future__ import annotations

import logging
import os
import re
from typing import Optional

from google.cloud import storage

logger = logging.getLogger(__name__)

PATIENT_DOCS_BUCKET = os.getenv("PATIENT_DOCS_BUCKET", "")
PATIENT_DOCS_PREFIX = os.getenv("PATIENT_DOCS_PREFIX", "")
_MAX_CONTEXT_CHARS = 5500
_MAX_SNIPPETS = 5


def _is_supported_path(path: str, selected_types: set[str]) -> bool:
    lower = path.lower()
    if lower.endswith(".keep"):
        return False
    if not (lower.endswith(".md") or lower.endswith(".txt")):
        return False
    return any(f"/{doc_type}/" in lower for doc_type in selected_types)


def _split_chunks(text: str) -> list[str]:
    base = text.replace("\r\n", "\n")
    pieces = re.split(r"\n\s*\n", base)
    chunks = [p.strip() for p in pieces if p and p.strip()]
    if chunks:
        return chunks
    fallback = [line.strip() for line in base.split("\n") if line.strip()]
    return fallback


def _score_chunk(path: str, chunk: str, terms: list[str]) -> int:
    hay_path = path.lower()
    hay_chunk = chunk.lower()
    score = 0
    for term in terms:
        t = term.lower().strip()
        if not t:
            continue
        if t in hay_path:
            score += 3
        if t in hay_chunk:
            score += min(6, hay_chunk.count(t))
    return score


def _get_doc_type_from_path(path: str, selected_types: set[str]) -> str:
    lower = path.lower()
    for doc_type in selected_types:
        token = f"/{doc_type}/"
        if token in lower:
            return doc_type
    return "unknown"


def build_patient_document_context(selection: Optional[dict]) -> str:
    selection = selection or {}
    selected_types = list(selection.get("needed_document_types", []) or [])
    query_terms = list(selection.get("query_terms", []) or [])

    if not selected_types:
        return "No patient-specific unstructured document context was selected for this request."

    if not PATIENT_DOCS_BUCKET or not PATIENT_DOCS_PREFIX:
        return (
            "PATIENT-SPECIFIC DOCUMENT CONTEXT:\n"
            "Source: Google Cloud Storage\n"
            "No patient-specific document context was loaded because PATIENT_DOCS_BUCKET and/or "
            "PATIENT_DOCS_PREFIX is not configured.\n"
        )

    selected_type_set = set(selected_types)

    try:
        client = storage.Client()
        blobs = list(client.list_blobs(PATIENT_DOCS_BUCKET, prefix=PATIENT_DOCS_PREFIX))
    except Exception as exc:
        logger.warning("patient_docs retrieval_error=%s", type(exc).__name__)
        return (
            "PATIENT-SPECIFIC DOCUMENT CONTEXT:\n"
            "Source: Google Cloud Storage\n"
            f"Bucket: {PATIENT_DOCS_BUCKET}\n"
            f"Prefix: {PATIENT_DOCS_PREFIX}\n"
            "Note: These are selected snippets, not the full patient document set.\n\n"
            "No relevant patient-specific document snippets were found.\n\n"
            "Document context status:\n"
            f"- selected_document_types: {selected_types}\n"
            f"- query_terms: {query_terms}\n"
            "- snippets_returned: 0\n"
            f"- retrieval_note: Document retrieval failed ({type(exc).__name__}).\n"
        )

    considered = 0
    scored_chunks: list[tuple[int, str, str, str]] = []

    for blob in blobs:
        path = blob.name
        if not _is_supported_path(path, selected_type_set):
            continue

        considered += 1
        try:
            text = blob.download_as_text()
        except Exception:
            continue

        for chunk in _split_chunks(text):
            score = _score_chunk(path, chunk, query_terms)
            if score <= 0:
                continue
            doc_type = _get_doc_type_from_path(path, selected_type_set)
            snippet = chunk[:650].strip()
            if snippet:
                scored_chunks.append((score, path, doc_type, snippet))

    scored_chunks.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = scored_chunks[:_MAX_SNIPPETS]

    logger.info(
        "patient_docs selected_types=%s query_term_count=%d blobs_considered=%d snippets_returned=%d",
        selected_types,
        len(query_terms),
        considered,
        len(top),
    )

    if not top:
        out = (
            "PATIENT-SPECIFIC DOCUMENT CONTEXT:\n"
            "Source: Google Cloud Storage\n"
            f"Bucket: {PATIENT_DOCS_BUCKET}\n"
            f"Prefix: {PATIENT_DOCS_PREFIX}\n"
            "Note: These are selected snippets, not the full patient document set.\n\n"
            "No relevant patient-specific document snippets were found.\n\n"
            "Document context status:\n"
            f"- selected_document_types: {selected_types}\n"
            f"- query_terms: {query_terms}\n"
            "- snippets_returned: 0\n"
            "- retrieval_note: No matching snippets for selected terms and document types.\n"
        )
        logger.info("patient_docs context_length=%d", len(out))
        return out

    lines = [
        "PATIENT-SPECIFIC DOCUMENT CONTEXT:",
        "Source: Google Cloud Storage",
        f"Bucket: {PATIENT_DOCS_BUCKET}",
        f"Prefix: {PATIENT_DOCS_PREFIX}",
        "Note: These are selected snippets, not the full patient document set.",
        "",
        "Retrieved snippets:",
    ]

    for idx, (_, path, doc_type, snippet) in enumerate(top, start=1):
        lines.extend(
            [
                f"{idx}. Document: {path}",
                f"   Type: {doc_type}",
                "   Snippet:",
                f"   {snippet}",
                "",
            ]
        )

    lines.extend(
        [
            "Document context status:",
            f"- selected_document_types: {selected_types}",
            f"- query_terms: {query_terms}",
            f"- snippets_returned: {len(top)}",
            "- retrieval_note: Retrieved ranked snippets from selected folders only.",
        ]
    )

    out = "\n".join(lines).strip()
    if len(out) > _MAX_CONTEXT_CHARS:
        out = out[: _MAX_CONTEXT_CHARS - 64].rstrip() + "\n\n[truncated to context limit]"

    logger.info("patient_docs context_length=%d", len(out))
    return out
