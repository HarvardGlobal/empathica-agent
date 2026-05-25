"""Deterministic user->patient identity mapping (no LLM decision path)."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

IDENTITY_MAP_COLLECTION = os.getenv("IDENTITY_MAP_COLLECTION", "patient_identity_map")


@dataclass
class PatientIdentity:
    user_id: str
    fhir_patient_id: str
    docs_prefix: str
    status: str
    tenant: str


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
      - docs_prefix (string, optional; defaults to patients/<fhir_patient_id>/)
      - status (string, optional; defaults to active)
      - tenant (string, optional; defaults to default)
    """
    uid = (user_id or "").strip()
    if not uid:
        return None

    client = firestore.Client()
    snap = client.collection(IDENTITY_MAP_COLLECTION).document(uid).get()
    if not snap.exists:
        logger.info("identity_map lookup user_id=%s result=not_found", uid)
        return None

    data = snap.to_dict() or {}
    fhir_patient_id = str(data.get("fhir_patient_id") or "").strip()
    if not fhir_patient_id:
        logger.warning("identity_map lookup user_id=%s result=invalid_missing_patient_id", uid)
        return None

    docs_prefix = _normalize_prefix(str(data.get("docs_prefix") or f"patients/{fhir_patient_id}/"))
    status = str(data.get("status") or "active").strip().lower()
    tenant = str(data.get("tenant") or "default").strip()

    identity = PatientIdentity(
        user_id=uid,
        fhir_patient_id=fhir_patient_id,
        docs_prefix=docs_prefix,
        status=status,
        tenant=tenant,
    )
    logger.info(
        "identity_map lookup user_id=%s result=ok patient_id=%s docs_prefix=%s status=%s tenant=%s",
        uid,
        identity.fhir_patient_id,
        identity.docs_prefix,
        identity.status,
        identity.tenant,
    )
    return identity

