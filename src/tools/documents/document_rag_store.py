from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

FIRESTORE_DOCUMENT_RAG_DATABASE_ID = os.getenv("FIRESTORE_DOCUMENT_RAG_DATABASE_ID", "empathica-document-rag")
FIRESTORE_DOCUMENT_COLLECTION = os.getenv("FIRESTORE_DOCUMENT_COLLECTION", "patient_documents")
FIRESTORE_CHUNK_COLLECTION = os.getenv("FIRESTORE_CHUNK_COLLECTION", "patient_document_chunks")
FIRESTORE_INDEXING_RUNS_COLLECTION = os.getenv("FIRESTORE_INDEXING_RUNS_COLLECTION", "indexing_runs")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_document_id(source_path: str) -> str:
    return hashlib.sha256((source_path or "").encode("utf-8")).hexdigest()


def make_chunk_id(document_id: str, chunk_index: int) -> str:
    return f"{document_id}:{chunk_index}"


def _client() -> firestore.Client:
    project = os.getenv("VERTEX_AI_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT") or None
    kwargs: dict[str, Any] = {"database": FIRESTORE_DOCUMENT_RAG_DATABASE_ID}
    if project:
        kwargs["project"] = project
    try:
        return firestore.Client(**kwargs)
    except TypeError as exc:
        raise RuntimeError(
            "The installed google-cloud-firestore client does not support named databases; "
            "document RAG must not fall back to the identity database."
        ) from exc


def get_document_record(source_path: str) -> dict[str, Any] | None:
    document_id = make_document_id(source_path)
    snapshot = _client().collection(FIRESTORE_DOCUMENT_COLLECTION).document(document_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    data.setdefault("document_id", document_id)
    return data


def upsert_document_record(record: dict[str, Any]) -> str:
    source_path = str(record.get("source_path") or "")
    document_id = str(record.get("document_id") or make_document_id(source_path))
    payload = {
        **record,
        "document_id": document_id,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if not record.get("created_at"):
        payload["created_at"] = firestore.SERVER_TIMESTAMP
    _client().collection(FIRESTORE_DOCUMENT_COLLECTION).document(document_id).set(payload, merge=True)
    return document_id


def replace_document_chunks(document_id: str, chunks: list[dict[str, Any]]) -> None:
    client = _client()
    query = client.collection(FIRESTORE_CHUNK_COLLECTION).where("document_id", "==", document_id)
    batch = client.batch()
    operations = 0
    for existing in query.stream():
        batch.delete(existing.reference)
        operations += 1
        if operations >= 450:
            batch.commit()
            batch = client.batch()
            operations = 0
    if operations:
        batch.commit()

    if not chunks:
        return

    batch = client.batch()
    operations = 0
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or make_chunk_id(document_id, int(chunk.get("chunk_index", 0))))
        payload = {
            **chunk,
            "chunk_id": chunk_id,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        batch.set(client.collection(FIRESTORE_CHUNK_COLLECTION).document(chunk_id), payload, merge=True)
        operations += 1
        if operations >= 450:
            batch.commit()
            batch = client.batch()
            operations = 0
    if operations:
        batch.commit()


def write_indexing_run(summary: dict[str, Any]) -> str:
    run_id = str(summary.get("run_id") or utcnow().strftime("%Y%m%dT%H%M%SZ"))
    payload = {**summary, "run_id": run_id, "created_at": firestore.SERVER_TIMESTAMP}
    _client().collection(FIRESTORE_INDEXING_RUNS_COLLECTION).document(run_id).set(payload, merge=True)
    return run_id


def query_patient_chunks(patient_id: str) -> list[dict[str, Any]]:
    query = _client().collection(FIRESTORE_CHUNK_COLLECTION).where("patient_id", "==", patient_id)
    chunks = []
    for doc in query.stream():
        data = doc.to_dict() or {}
        data.setdefault("chunk_id", doc.id)
        chunks.append(data)
    return chunks


def store_document_and_chunks(document_record: dict[str, Any], chunks: list[dict[str, Any]]) -> str:
    document_id = upsert_document_record(document_record)
    replace_document_chunks(document_id, chunks)
    return document_id
