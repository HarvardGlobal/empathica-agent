from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from google.cloud import storage

PATIENT_DOCS_BUCKET = os.getenv("PATIENT_DOCS_BUCKET", "")
PATIENT_DOCS_PREFIX = os.getenv("PATIENT_DOCS_PREFIX", "patients/")
SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass(frozen=True)
class IngestedDocument:
    patient_id: str
    source_path: str
    file_name: str
    content: str
    content_hash: str


def normalize_docs_prefix(prefix: str | None = None) -> str:
    value = (prefix if prefix is not None else PATIENT_DOCS_PREFIX or "").strip()
    if not value:
        return ""
    return value if value.endswith("/") else f"{value}/"


def extract_patient_id_from_source_path(source_path: str, prefix: str | None = None) -> str:
    prefix_value = normalize_docs_prefix(prefix)
    path = str(PurePosixPath(source_path)).lstrip("/")
    if prefix_value and path.startswith(prefix_value):
        path = path[len(prefix_value) :]
    parts = [part for part in path.split("/") if part]
    return parts[0] if parts else ""


def is_supported_document(source_path: str) -> bool:
    lower = (source_path or "").lower()
    if lower.endswith(".keep"):
        return False
    return any(lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS)


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def read_gcs_text(bucket_name: str, source_path: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    return bucket.blob(source_path).download_as_text()


def list_gcs_blobs(bucket_name: str, prefix: str) -> Iterable[object]:
    client = storage.Client()
    return client.list_blobs(bucket_name, prefix=prefix)


def ingest_document(bucket_name: str, source_path: str, prefix: str | None = None) -> IngestedDocument:
    content = read_gcs_text(bucket_name, source_path)
    return IngestedDocument(
        patient_id=extract_patient_id_from_source_path(source_path, prefix=prefix),
        source_path=source_path,
        file_name=source_path.split("/")[-1],
        content=content,
        content_hash=content_hash(content),
    )
