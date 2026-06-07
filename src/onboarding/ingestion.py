from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import os
import re
from typing import Any

import google.auth
from google.auth.transport.requests import Request
from google.cloud import storage
import httpx

from ..tools.patient.identity_map import PatientIdentity, upsert_patient_identity

logger = logging.getLogger(__name__)

FHIR_PROJECT_ID = os.getenv("FHIR_PROJECT_ID", "")
FHIR_LOCATION = os.getenv("FHIR_LOCATION", "")
FHIR_DATASET = os.getenv("FHIR_DATASET", "")
FHIR_STORE = os.getenv("FHIR_STORE", "")
PATIENT_DOCS_BUCKET = os.getenv("PATIENT_DOCS_BUCKET", "")
_DOC_TYPE_RULES_ENV = "PATIENT_DOC_TYPE_KEYWORDS_JSON"

_DEFAULT_DOC_TYPE_RULES: dict[str, list[str]] = {
    "medication_management": [
        "medication",
        "pharmacy",
        "drug",
        "dose",
        "supplement",
        "ibuprofen",
        "acetaminophen",
    ],
    "oncology_notes": [
        "oncology",
        "cancer",
        "tumor",
        "metastatic",
        "clinical trial",
        "chemotherapy",
        "lab",
        "treatment",
    ],
    "care_coordination": [
        "care coordination",
        "appointment",
        "support network",
        "communication",
        "daily life",
        "home health",
    ],
    "appointment_summaries": ["schedule", "calendar", "visit", "follow-up"],
    "communication_preferences": ["language", "literacy", "teach-back", "preferred communication"],
    "financial_access": ["insurance", "copay", "cost", "financial", "access"],
    "symptom_journal": ["symptom", "pain", "nausea", "fatigue", "sleep"],
}


@dataclass
class OnboardingResult:
    identity: PatientIdentity
    fhir_import_status: str
    fhir_patient_id: str
    docs_object_path: str
    docs_prefix: str


def _fhir_base() -> str:
    return (
        "https://healthcare.googleapis.com/v1/projects/"
        f"{FHIR_PROJECT_ID}/locations/{FHIR_LOCATION}/datasets/{FHIR_DATASET}"
        f"/fhirStores/{FHIR_STORE}/fhir"
    )


def _auth_token() -> str:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token


def _is_fhir_env_configured() -> bool:
    return all([FHIR_PROJECT_ID, FHIR_LOCATION, FHIR_DATASET, FHIR_STORE])


def _extract_patient_id_from_fhir_payload(payload: dict[str, Any]) -> str:
    resource_type = str(payload.get("resourceType") or "")
    if resource_type == "Patient":
        pid = str(payload.get("id") or "").strip()
        if pid:
            return pid
    if resource_type == "Bundle":
        for entry in payload.get("entry", []) or []:
            if not isinstance(entry, dict):
                continue
            res = entry.get("resource")
            if isinstance(res, dict) and str(res.get("resourceType") or "") == "Patient":
                pid = str(res.get("id") or "").strip()
                if pid:
                    return pid
    raise ValueError("FHIR payload must include a Patient resource with an id.")


def _import_fhir_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not _is_fhir_env_configured():
        raise ValueError("FHIR environment is not configured (FHIR_PROJECT_ID/LOCATION/DATASET/STORE).")
    token = _auth_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/fhir+json; charset=utf-8",
        "Accept": "application/fhir+json",
    }
    # GCP FHIR store does not execute Bundle type=collection at the root endpoint.
    # For collection bundles we upsert each contained resource deterministically.
    if str(payload.get("resourceType") or "") == "Bundle" and str(payload.get("type") or "") == "collection":
        results: list[dict[str, Any]] = []
        with httpx.Client(timeout=30.0) as client:
            for entry in payload.get("entry", []) or []:
                if not isinstance(entry, dict):
                    continue
                resource = entry.get("resource")
                if not isinstance(resource, dict):
                    continue
                rtype = str(resource.get("resourceType") or "").strip()
                if not rtype:
                    continue
                rid = str(resource.get("id") or "").strip()
                if rid:
                    # Preserve declared IDs so internal references remain stable.
                    url = f"{_fhir_base()}/{rtype}/{rid}"
                    resp = client.put(url, headers=headers, json=resource)
                else:
                    url = f"{_fhir_base()}/{rtype}"
                    resp = client.post(url, headers=headers, json=resource)
                if resp.status_code >= 400:
                    raise ValueError(f"FHIR import failed for {rtype}/{rid or '[new]'}: {resp.status_code} {resp.text[:500]}")
                try:
                    results.append(resp.json())
                except Exception:
                    results.append({"resourceType": rtype, "status_code": resp.status_code})
        return {"resourceType": "Bundle", "type": "collection-import-result", "entry": results}

    resp = httpx.post(_fhir_base(), headers=headers, json=payload, timeout=30.0)
    if resp.status_code >= 400:
        raise ValueError(f"FHIR import failed: {resp.status_code} {resp.text[:500]}")
    try:
        return resp.json()
    except Exception:
        return {"status_code": resp.status_code}


def _upload_unstructured_blob(*, patient_id: str, filename: str, content: bytes) -> tuple[str, str]:
    if not PATIENT_DOCS_BUCKET:
        raise ValueError("PATIENT_DOCS_BUCKET is not configured.")
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    docs_prefix = f"patients/{patient_id}/"
    object_path = f"{docs_prefix}uploads/{now}_{filename}"
    client = storage.Client()
    bucket = client.bucket(PATIENT_DOCS_BUCKET)
    blob = bucket.blob(object_path)
    blob.upload_from_string(content)
    return docs_prefix, object_path


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, content) blocks using ##/### headings."""
    normalized = text.replace("\r\n", "\n")
    parts = re.split(r"(?m)^##+\s+", normalized)
    sections: list[tuple[str, str]] = []
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        lines = chunk.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections.append((heading, body))
    return sections


def _load_doc_type_rules() -> dict[str, list[str]]:
    raw = os.getenv(_DOC_TYPE_RULES_ENV, "").strip()
    if not raw:
        return _DEFAULT_DOC_TYPE_RULES
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invalid %s, using defaults", _DOC_TYPE_RULES_ENV)
        return _DEFAULT_DOC_TYPE_RULES
    if not isinstance(parsed, dict):
        logger.warning("non-dict %s, using defaults", _DOC_TYPE_RULES_ENV)
        return _DEFAULT_DOC_TYPE_RULES

    out: dict[str, list[str]] = {}
    for key, val in parsed.items():
        if not isinstance(key, str) or not isinstance(val, list):
            continue
        words = [str(x).strip().lower() for x in val if str(x).strip()]
        if words:
            out[key.strip()] = words
    return out or _DEFAULT_DOC_TYPE_RULES


def _doc_type_for_section(heading: str, body: str, rules: dict[str, list[str]], allowed: set[str]) -> str:
    text = f"{heading}\n{body}".lower()
    for doc_type, keywords in rules.items():
        if doc_type not in allowed:
            continue
        if any(k in text for k in keywords):
            return doc_type
    return "general_notes" if "general_notes" in allowed else next(iter(allowed))


def _upload_typed_unstructured_blobs(
    *,
    patient_id: str,
    content: bytes,
    target_document_types: list[str] | None = None,
) -> list[str]:
    """Create typed markdown docs under expected retrieval folders."""
    if not PATIENT_DOCS_BUCKET:
        raise ValueError("PATIENT_DOCS_BUCKET is not configured.")

    text = content.decode("utf-8", errors="ignore")
    sections = _split_markdown_sections(text)
    if not sections:
        return []

    rules = _load_doc_type_rules()
    allowed_types = {k for k in rules.keys()}
    allowed_types.add("general_notes")
    if target_document_types:
        allowed_types.update({x.strip() for x in target_document_types if x and x.strip()})

    grouped: dict[str, list[str]] = {dtype: [] for dtype in sorted(allowed_types)}
    for heading, body in sections:
        dtype = _doc_type_for_section(heading, body, rules, allowed_types)
        grouped.setdefault(dtype, []).append(f"## {heading}\n{body}".strip())

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    docs_prefix = f"patients/{patient_id}/"
    client = storage.Client()
    bucket = client.bucket(PATIENT_DOCS_BUCKET)
    created_paths: list[str] = []

    for dtype, blocks in grouped.items():
        if not blocks:
            continue
        object_path = f"{docs_prefix}{dtype}/{now}_{dtype}_summary.md"
        payload = "\n\n".join(blocks).strip() + "\n"
        bucket.blob(object_path).upload_from_string(payload.encode("utf-8"))
        created_paths.append(object_path)

    return created_paths


def onboard_user_with_files(
    *,
    user_id: str,
    structured_fhir_json: dict[str, Any],
    unstructured_filename: str,
    unstructured_bytes: bytes,
    tenant: str = "default",
    status: str = "active",
    target_document_types: list[str] | None = None,
) -> OnboardingResult:
    patient_id = _extract_patient_id_from_fhir_payload(structured_fhir_json)
    fhir_import_response = _import_fhir_payload(structured_fhir_json)
    docs_prefix, docs_object_path = _upload_unstructured_blob(
        patient_id=patient_id,
        filename=unstructured_filename,
        content=unstructured_bytes,
    )
    typed_paths = _upload_typed_unstructured_blobs(
        patient_id=patient_id,
        content=unstructured_bytes,
        target_document_types=target_document_types,
    )
    identity = upsert_patient_identity(
        user_id=user_id,
        fhir_patient_id=patient_id,
        document_patient_id=patient_id,
        document_docs_prefix=docs_prefix,
        status=status,
        tenant=tenant,
    )
    logger.info(
        "onboarding completed user_id=%s patient_id=%s docs_object_path=%s typed_docs=%s",
        user_id,
        patient_id,
        docs_object_path,
        typed_paths,
    )
    return OnboardingResult(
        identity=identity,
        fhir_import_status=str(fhir_import_response.get("resourceType") or "ok"),
        fhir_patient_id=patient_id,
        docs_object_path=docs_object_path,
        docs_prefix=docs_prefix,
    )
