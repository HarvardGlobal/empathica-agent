"""Deterministic user->patient identity mapping (no LLM decision path)."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

IDENTITY_MAP_COLLECTION = os.getenv("IDENTITY_MAP_COLLECTION", "patient_identity_map")
FIRESTORE_DATABASE_ID = os.getenv(
    "FIRESTORE_IDENTITY_DATABASE_ID",
    os.getenv("FIRESTORE_DATABASE_ID", "(default)"),
)


@dataclass
class PatientIdentity:
    user_id: str
    tenant: str
    status: str
    fhir_patient_id: str
    document_patient_id: str
    docs_prefix: str

    @property
    def document_docs_prefix(self) -> str:
        return self.docs_prefix


def _normalize_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return p
    return p if p.endswith("/") else f"{p}/"


def _derive_document_patient_id_from_prefix(prefix: str) -> str:
    normalized = _normalize_prefix(prefix)
    if not normalized:
        return ""
    stripped = normalized.strip("/")
    parts = [part for part in stripped.split("/") if part]
    if len(parts) >= 2 and parts[0] == "patients":
        return parts[1].strip()
    return ""


def resolve_patient_identity(user_id: str) -> Optional[PatientIdentity]:
    """Resolve deterministic identity mapping from Firestore.

    Expected document schema (collection: patient_identity_map, doc id: user_id):
      - user_id (string)
      - fhir_patient_id (string, required)
      - document_patient_id (string, optional; derived from docs_prefix if omitted)
      - docs_prefix (string, optional; preferred document storage prefix)
      - document_docs_prefix (string, optional legacy alias)
      - status (string, optional; defaults to active)
      - tenant (string, optional; defaults to default)
    """
    uid = (user_id or "").strip()
    if not uid:
        return None

    client = firestore.Client(database=FIRESTORE_DATABASE_ID)
    snap = client.collection(IDENTITY_MAP_COLLECTION).document(uid).get()
    if not snap.exists:
        logger.info("identity_map lookup user_id=%s result=not_found", uid)
        return None

    data = snap.to_dict() or {}
    fhir_patient_id = str(data.get("fhir_patient_id") or "").strip()
    if not fhir_patient_id:
        logger.warning("identity_map lookup user_id=%s result=invalid_missing_patient_id", uid)
        return None

    docs_prefix_raw = str(data.get("docs_prefix") or data.get("document_docs_prefix") or "").strip()
    explicit_document_patient_id = str(data.get("document_patient_id") or "").strip()
    document_patient_id = explicit_document_patient_id
    if not document_patient_id and docs_prefix_raw:
        document_patient_id = _derive_document_patient_id_from_prefix(docs_prefix_raw)
    if not document_patient_id:
        document_patient_id = fhir_patient_id

    document_docs_prefix = _normalize_prefix(
        docs_prefix_raw or f"patients/{document_patient_id}/"
    )
    status = str(data.get("status") or "active").strip().lower()
    tenant = str(data.get("tenant") or "default").strip()

    identity = PatientIdentity(
        user_id=uid,
        tenant=tenant,
        status=status,
        fhir_patient_id=fhir_patient_id,
        document_patient_id=document_patient_id,
        docs_prefix=document_docs_prefix,
    )
    logger.info(
        "identity_map lookup user_id=%s result=ok fhir_patient_id=%s document_patient_id=%s docs_prefix=%s status=%s tenant=%s",
        uid,
        identity.fhir_patient_id,
        identity.document_patient_id,
        identity.docs_prefix,
        identity.status,
        identity.tenant,
    )
    return identity


def upsert_patient_identity(
    *,
    user_id: str,
    fhir_patient_id: str,
    docs_prefix: str | None = None,
    document_patient_id: str | None = None,
    document_docs_prefix: str | None = None,
    status: str = "active",
    tenant: str = "default",
) -> PatientIdentity:
    uid = (user_id or "").strip()
    pid = (fhir_patient_id or "").strip()
    if not uid or not pid:
        raise ValueError("user_id and fhir_patient_id are required.")

    normalized_prefix = _normalize_prefix(document_docs_prefix or docs_prefix or "")
    doc_pid = (document_patient_id or "").strip()
    if not doc_pid and normalized_prefix:
        doc_pid = _derive_document_patient_id_from_prefix(normalized_prefix)
    if not doc_pid:
        doc_pid = pid
    if not normalized_prefix:
        normalized_prefix = _normalize_prefix(f"patients/{doc_pid}/")
    status_norm = (status or "active").strip().lower()
    tenant_norm = (tenant or "default").strip()

    payload = {
        "user_id": uid,
        "fhir_patient_id": pid,
        "document_patient_id": doc_pid,
        "document_docs_prefix": normalized_prefix,
        "docs_prefix": normalized_prefix,
        "status": status_norm,
        "tenant": tenant_norm,
    }

    client = firestore.Client(database=FIRESTORE_DATABASE_ID)
    client.collection(IDENTITY_MAP_COLLECTION).document(uid).set(payload, merge=True)
    logger.info(
        "identity_map upsert user_id=%s fhir_patient_id=%s document_patient_id=%s docs_prefix=%s status=%s tenant=%s",
        uid,
        pid,
        doc_pid,
        normalized_prefix,
        status_norm,
        tenant_norm,
    )
    return PatientIdentity(
        user_id=uid,
        tenant=tenant_norm,
        status=status_norm,
        fhir_patient_id=pid,
        document_patient_id=doc_pid,
        docs_prefix=normalized_prefix,
    )
