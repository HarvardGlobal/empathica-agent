from __future__ import annotations

import logging
import os
import re
from typing import Optional

from google.cloud import storage

logger = logging.getLogger(__name__)

PATIENT_DOCS_BUCKET = os.getenv("PATIENT_DOCS_BUCKET", "")
_MAX_CONTEXT_CHARS = 5500
_MAX_SNIPPETS = 5


def _is_supported_path(path: str, selected_types: set[str]) -> bool:
    lower = path.lower()
    if lower.endswith(".keep"):
        return False
    if not (lower.endswith(".md") or lower.endswith(".txt")):
        return False
    return any(f"/{doc_type}/" in lower for doc_type in selected_types)


def _is_uploads_path(path: str) -> bool:
    lower = path.lower()
    if lower.endswith(".keep"):
        return False
    if not (lower.endswith(".md") or lower.endswith(".txt")):
        return False
    return "/uploads/" in lower


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


def _collect_scored_chunks(
    *,
    blobs: list,
    query_terms: list[str],
    selected_type_set: set[str],
    include_uploads: bool,
) -> tuple[int, list[tuple[int, str, str, str]]]:
    considered = 0
    scored_chunks: list[tuple[int, str, str, str]] = []

    for blob in blobs:
        path = blob.name
        if include_uploads:
            if not _is_uploads_path(path):
                continue
        else:
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
            doc_type = "uploads" if include_uploads else _get_doc_type_from_path(path, selected_type_set)
            snippet = chunk[:650].strip()
            if snippet:
                scored_chunks.append((score, path, doc_type, snippet))

    return considered, scored_chunks


def build_patient_document_context(selection: Optional[dict], docs_prefix: str | None = None) -> str:
    selection = selection or {}
    selected_types = list(selection.get("needed_document_types", []) or [])
    query_terms = list(selection.get("query_terms", []) or [])

    if not selected_types:
        return "No patient-specific unstructured document context was selected for this request."

    selected_type_set = set(selected_types)
    bucket = PATIENT_DOCS_BUCKET or "unconfigured-bucket"
    prefix = (docs_prefix or "").strip()

    try:
        client = storage.Client()
        blobs = list(client.list_blobs(bucket, prefix=prefix))
    except Exception as exc:
        logger.warning("patient_docs retrieval_error=%s", type(exc).__name__)
        return (
            "PATIENT-SPECIFIC DOCUMENT CONTEXT:\n"
            "Source: Google Cloud Storage\n"
            f"Bucket: {bucket}\n"
            f"Prefix: {prefix}\n"
            "Note: These are selected snippets, not the full patient document set.\n\n"
            "No relevant patient-specific document snippets were found.\n\n"
            "Document context status:\n"
            f"- selected_document_types: {selected_types}\n"
            f"- query_terms: {query_terms}\n"
            "- snippets_returned: 0\n"
            f"- retrieval_note: Document retrieval failed ({type(exc).__name__}).\n"
        )

    considered, scored_chunks = _collect_scored_chunks(
        blobs=blobs,
        query_terms=query_terms,
        selected_type_set=selected_type_set,
        include_uploads=False,
    )

    scored_chunks.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = scored_chunks[:_MAX_SNIPPETS]
    used_uploads_fallback = False

    if not top:
        uploads_considered, uploads_chunks = _collect_scored_chunks(
            blobs=blobs,
            query_terms=query_terms,
            selected_type_set=selected_type_set,
            include_uploads=True,
        )
        considered += uploads_considered
        uploads_chunks.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top = uploads_chunks[:_MAX_SNIPPETS]
        used_uploads_fallback = bool(top)

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
            f"Bucket: {bucket}\n"
            f"Prefix: {prefix}\n"
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
        f"Bucket: {bucket}",
        f"Prefix: {prefix}",
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
            (
                "- retrieval_note: Retrieved ranked snippets from uploads fallback after no matches in selected folders."
                if used_uploads_fallback
                else "- retrieval_note: Retrieved ranked snippets from selected folders only."
            ),
        ]
    )

    out = "\n".join(lines).strip()
    if len(out) > _MAX_CONTEXT_CHARS:
        out = out[: _MAX_CONTEXT_CHARS - 64].rstrip() + "\n\n[truncated to context limit]"

    logger.info("patient_docs context_length=%d", len(out))
    return out
