from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import google.auth
from google.auth.transport.requests import Request
import httpx

from .medication_retrieval_plan_schema import MedicationRetrievalPlan

logger = logging.getLogger(__name__)

FHIR_PROJECT_ID = os.getenv("FHIR_PROJECT_ID", "")
FHIR_LOCATION = os.getenv("FHIR_LOCATION", "")
FHIR_DATASET = os.getenv("FHIR_DATASET", "")
FHIR_STORE = os.getenv("FHIR_STORE", "")


def _fhir_base() -> str:
    return (
        "https://healthcare.googleapis.com/v1/projects/"
        f"{FHIR_PROJECT_ID}/locations/{FHIR_LOCATION}/datasets/{FHIR_DATASET}"
        f"/fhirStores/{FHIR_STORE}/fhir"
    )


def _auth_token() -> str:
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        return creds.token
    except Exception as exc:
        logger.warning("fhir_med_auth_unavailable reason=%s", type(exc).__name__)
        return ""


def _get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    token = _auth_token()
    if not token:
        return None
    try:
        response = httpx.get(
            f"{_fhir_base()}/{path.lstrip('/')}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"},
            timeout=12.0,
        )
        if response.status_code != 200:
            return None
        return response.json()
    except Exception:
        return None


def _entries(bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict):
        return []
    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in entries:
        res = entry.get("resource") if isinstance(entry, dict) else None
        if isinstance(res, dict):
            out.append(res)
    return out


def _human_name(patient: dict[str, Any] | None) -> str:
    if not isinstance(patient, dict):
        return "Unknown Patient"
    names = patient.get("name", [])
    if names and isinstance(names[0], dict):
        given = " ".join(names[0].get("given", []) or [])
        family = names[0].get("family", "") or ""
        full = f"{given} {family}".strip()
        if full:
            return full
    return "Unknown Patient"


def _compute_age(birth_date: str | None) -> str:
    if not birth_date:
        return "unknown"
    try:
        dob = datetime.strptime(birth_date, "%Y-%m-%d").date()
        today = date.today()
        years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return str(max(years, 0))
    except Exception:
        return "unknown"


def _normalise_display_name(med: dict[str, Any]) -> str:
    name = ""
    cc = med.get("medicationCodeableConcept", {})
    if isinstance(cc, dict):
        name = str(cc.get("text") or "")
        if not name:
            coding = cc.get("coding", [])
            if coding and isinstance(coding[0], dict):
                name = str(coding[0].get("display") or "")
    if not name:
        name = str(med.get("medicationReference", {}).get("display", "") if isinstance(med.get("medicationReference"), dict) else "")
    if not name:
        name = "Unknown medication"
    return name


def _strip_strength_and_form(text: str) -> str:
    from .medication_resolver import normalize_free_text_medication
    return normalize_free_text_medication(text)


def _med_item(resource: dict[str, Any]) -> dict[str, Any]:
    display_name = _normalise_display_name(resource)
    normalized_name = _strip_strength_and_form(display_name)
    status = str(resource.get("status") or "unknown")
    effective = str(resource.get("effectiveDateTime") or resource.get("assertedDate") or "")
    dose = ""
    strength = ""
    route = ""
    frequency = ""
    dosage = resource.get("dosage", [])
    if dosage and isinstance(dosage, list) and isinstance(dosage[0], dict):
        first = dosage[0]
        route = str(first.get("route", {}).get("text") if isinstance(first.get("route"), dict) else first.get("route", "") or "")
        timing = first.get("timing", {})
        if isinstance(timing, dict):
            repeat = timing.get("repeat", {})
            if isinstance(repeat, dict):
                frequency = str(repeat.get("frequency") or repeat.get("period") or "")
        dose_q = first.get("doseAndRate", [])
        if dose_q and isinstance(dose_q, list) and isinstance(dose_q[0], dict):
            qty = dose_q[0].get("doseQuantity", {})
            if isinstance(qty, dict):
                dose = f"{qty.get('value')} {qty.get('unit', '')}".strip()
                strength = dose
    codes = []
    cc = resource.get("medicationCodeableConcept", {})
    if isinstance(cc, dict):
        codes = cc.get("coding", []) or []
    rxnorm = None
    ndc = None
    for coding in codes:
        if not isinstance(coding, dict):
            continue
        system = str(coding.get("system", "")).lower()
        code = coding.get("code")
        if "rxnorm" in system and code:
            rxnorm = str(code)
        if "ndc" in system and code:
            ndc = str(code)
    return {
        "raw_text": display_name,
        "display_name": display_name,
        "normalized_name": normalized_name or display_name.lower(),
        "generic_name": normalized_name or "",
        "brand_name": "",
        "status": status,
        "active_or_current": status in {"active", "unknown"} or "active" in status,
        "dose": dose,
        "strength": strength,
        "route": route,
        "frequency": frequency,
        "start_date": str(resource.get("effectiveDateTime") or ""),
        "end_date": str(resource.get("dateAsserted") or ""),
        "rxnorm_code": rxnorm,
        "ndc": ndc,
        "source_resource": "MedicationStatement",
        "confidence": "medium" if normalized_name else "low",
    }


def execute_fhir_medication_plan(plan: MedicationRetrievalPlan, patient_id: str) -> dict:
    requested_active = plan.requires_patient_medication_list or any(t.domain == "active_patient_medications" for t in plan.fhir_medication_targets)
    if not requested_active:
        return {
            "patient_id": patient_id,
            "status": "not_requested",
            "medications": [],
            "missing_details": [],
            "warnings": [],
            "source_trace": [],
            "configured": bool(all([FHIR_PROJECT_ID, FHIR_LOCATION, FHIR_DATASET, FHIR_STORE])),
        }

    bundle = _get_json("MedicationStatement", params={"subject": f"Patient/{patient_id}"})
    entries = _entries(bundle)
    meds = [_med_item(entry) for entry in entries]
    active_meds = [m for m in meds if m["active_or_current"]]

    # de-duplicate by normalized_name + display_name
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for med in active_meds or meds:
        key = (med["normalized_name"], med["display_name"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(med)

    return {
        "patient_id": patient_id,
        "status": "available" if deduped else "unavailable",
        "medications": deduped[:20],
        "missing_details": [] if deduped else ["No active MedicationStatement resources were found."],
        "warnings": [],
        "source_trace": [{"resource": "MedicationStatement", "count": len(entries), "returned": len(deduped)}],
        "configured": bool(all([FHIR_PROJECT_ID, FHIR_LOCATION, FHIR_DATASET, FHIR_STORE])),
    }
