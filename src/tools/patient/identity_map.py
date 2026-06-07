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
    fhir_patient_id: str
    document_patient_id: str
    document_docs_prefix: str
    status: str
    tenant: str

    @property
    def docs_prefix(self) -> str:
        return self.document_docs_prefix


def _normalize_prefix(prefix: str) -> str:
    p = (prefix or "").strip()
    if not p:
        return p
    return p if p.endswith("/") else f"{p}/"


def resolve_patient_identity(user_id: str) -> Optional[PatientIdentity]:
    """Resolve deterministic identity mapping from Firestore.

    Expected document schema (collection: patient_identity_map, doc id: user_id):
      - user_id (string)
      - fhir_patient_id (string, required)
      - document_patient_id (string, optional; defaults to fhir_patient_id)
      - document_docs_prefix (string, optional; defaults to patients/<document_patient_id>/)
      - docs_prefix (string, optional legacy alias; defaults to patients/<document_patient_id>/)
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

    document_patient_id = str(data.get("document_patient_id") or fhir_patient_id).strip() or fhir_patient_id
    document_docs_prefix = _normalize_prefix(
        str(
            data.get("document_docs_prefix")
            or data.get("docs_prefix")
            or f"patients/{document_patient_id}/"
        )
    )
    status = str(data.get("status") or "active").strip().lower()
    tenant = str(data.get("tenant") or "default").strip()

    identity = PatientIdentity(
        user_id=uid,
        fhir_patient_id=fhir_patient_id,
        document_patient_id=document_patient_id,
        document_docs_prefix=document_docs_prefix,
        status=status,
        tenant=tenant,
    )
    logger.info(
        "identity_map lookup user_id=%s result=ok fhir_patient_id=%s document_patient_id=%s docs_prefix=%s status=%s tenant=%s",
        uid,
        identity.fhir_patient_id,
        identity.document_patient_id,
        identity.document_docs_prefix,
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

    doc_pid = (document_patient_id or pid).strip() or pid
    normalized_prefix = _normalize_prefix(document_docs_prefix or docs_prefix or f"patients/{doc_pid}/")
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
        fhir_patient_id=pid,
        document_patient_id=doc_pid,
        document_docs_prefix=normalized_prefix,
        status=status_norm,
        tenant=tenant_norm,
    )
