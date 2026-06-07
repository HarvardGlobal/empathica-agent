from __future__ import annotations

import os
from datetime import datetime, timezone
import logging

from .document_chunker import chunk_text
from .document_embedding import EMBEDDING_MODEL_NAME, embed_text
from .document_ingestion import (
    PATIENT_DOCS_BUCKET,
    PATIENT_DOCS_PREFIX,
    content_hash,
    extract_patient_id_from_source_path,
    is_supported_document,
    list_gcs_blobs,
    read_gcs_text,
)
from .document_rag_store import get_document_record, store_document_and_chunks, write_indexing_run, make_document_id

logger = logging.getLogger(__name__)


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> None:
    bucket_name = os.getenv("PATIENT_DOCS_BUCKET", PATIENT_DOCS_BUCKET).strip()
    prefix = os.getenv("PATIENT_DOCS_PREFIX", PATIENT_DOCS_PREFIX).strip()
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    if not bucket_name:
        raise RuntimeError("PATIENT_DOCS_BUCKET is required.")

    processed = 0
    skipped = 0
    indexed = 0
    errors = 0
    chunks_created = 0
    indexed_documents: list[str] = []

    blobs = list(list_gcs_blobs(bucket_name, prefix))
    logger.info(
        "document_rag_indexing_start bucket=%s prefix=%s embedding_model=%s firestore_database=%s blob_count=%d",
        bucket_name,
        prefix,
        EMBEDDING_MODEL_NAME,
        os.getenv("FIRESTORE_DOCUMENT_RAG_DATABASE_ID", "empathica-document-rag"),
        len(blobs),
    )
    for blob in blobs:
        source_path = str(getattr(blob, "name", "") or "")
        if not source_path or not is_supported_document(source_path):
            continue

        patient_id = extract_patient_id_from_source_path(source_path, prefix=prefix)
        if not patient_id:
            continue

        processed += 1
        try:
            text = read_gcs_text(bucket_name, source_path)
            doc_hash = content_hash(text)
            existing = get_document_record(source_path)
            if (
                existing
                and existing.get("content_hash") == doc_hash
                and existing.get("embedding_model") == EMBEDDING_MODEL_NAME
                and existing.get("indexed") is True
            ):
                skipped += 1
                continue

            document_id = str(existing.get("document_id") if existing else make_document_id(source_path))
            file_name = source_path.split("/")[-1]
            chunks = chunk_text(
                text,
                patient_id=patient_id,
                source_path=source_path,
                file_name=file_name,
                document_id=document_id,
            )
            chunk_records = []
            for chunk in chunks:
                chunk_records.append(
                    {
                        "chunk_id": f"{document_id}:{chunk.chunk_index}",
                        "document_id": document_id,
                        "patient_id": patient_id,
                        "source_path": source_path,
                        "file_name": file_name,
                        "chunk_index": chunk.chunk_index,
                        "chunk_text": chunk.chunk_text,
                        "embedding": embed_text(chunk.chunk_text),
                        "embedding_model": EMBEDDING_MODEL_NAME,
                    }
                )
            chunks_created += len(chunk_records)

            store_document_and_chunks(
                {
                    "document_id": document_id,
                    "patient_id": patient_id,
                    "source_path": source_path,
                    "file_name": file_name,
                    "content_hash": doc_hash,
                    "indexed": True,
                    "chunk_count": len(chunk_records),
                    "embedding_model": EMBEDDING_MODEL_NAME,
                    "indexed_at": datetime.now(timezone.utc),
                },
                chunk_records,
            )
            indexed += 1
            indexed_documents.append(source_path)
        except Exception:
            errors += 1

    write_indexing_run(
        {
            "run_id": _utc_run_id(),
            "bucket": bucket_name,
            "prefix": prefix,
            "processed": processed,
            "skipped": skipped,
            "indexed": indexed,
            "errors": errors,
            "embedding_model": EMBEDDING_MODEL_NAME,
            "indexed_documents": indexed_documents,
        }
    )
    logger.info(
        "document_rag_indexing_complete bucket=%s prefix=%s processed=%d skipped=%d indexed=%d errors=%d chunks=%d embedding_model=%s firestore_database=%s",
        bucket_name,
        prefix,
        processed,
        skipped,
        indexed,
        errors,
        chunks_created,
        EMBEDDING_MODEL_NAME,
        os.getenv("FIRESTORE_DOCUMENT_RAG_DATABASE_ID", "empathica-document-rag"),
    )


if __name__ == "__main__":
    main()
