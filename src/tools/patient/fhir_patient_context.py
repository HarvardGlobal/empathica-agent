"""Selected FHIR patient context retrieval (Google Cloud Healthcare API)."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any

import google.auth
from google.auth.transport.requests import Request
import httpx

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


def _is_fhir_configured() -> bool:
    return all([FHIR_PROJECT_ID, FHIR_LOCATION, FHIR_DATASET, FHIR_STORE])


def _auth_token() -> str:
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        return creds.token
    except Exception as exc:
        logger.warning("fhir_auth_unavailable reason=%s", type(exc).__name__)
        return ""


def _fhir_get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    token = _auth_token()
    if not token:
        return None
    url = f"{_fhir_base()}/{path.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"}
    try:
        r = httpx.get(url, params=params, headers=headers, timeout=12.0)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _bundle_entries(bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict):
        return []
    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return []
    out = []
    for e in entries:
        if isinstance(e, dict) and isinstance(e.get("resource"), dict):
            out.append(e["resource"])
    return out


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


def _human_name(patient: dict[str, Any]) -> str:
    names = patient.get("name", []) if isinstance(patient, dict) else []
    if names and isinstance(names[0], dict):
        given = " ".join(names[0].get("given", []) or [])
        family = names[0].get("family", "") or ""
        full = f"{given} {family}".strip()
        if full:
            return full
    return "Unknown Patient"


def _med_name(ms: dict[str, Any]) -> str:
    cc = ms.get("medicationCodeableConcept", {})
    if isinstance(cc, dict):
        text = cc.get("text")
        if text:
            return str(text)
        coding = cc.get("coding", [])
        if coding and isinstance(coding[0], dict):
            return str(coding[0].get("display") or "Unknown medication")
    return "Unknown medication"


def _allergy_name(ai: dict[str, Any]) -> str:
    cc = ai.get("code", {})
    if isinstance(cc, dict):
        text = cc.get("text")
        if text:
            return str(text)
        coding = cc.get("coding", [])
        if coding and isinstance(coding[0], dict):
            return str(coding[0].get("display") or "Unknown allergy")
    return "Unknown allergy"


def _condition_name(c: dict[str, Any]) -> str:
    cc = c.get("code", {})
    if isinstance(cc, dict):
        text = cc.get("text")
        if text:
            return str(text)
        coding = cc.get("coding", [])
        if coding and isinstance(coding[0], dict):
            return str(coding[0].get("display") or "Unknown condition")
    return "Unknown condition"


def _obs_name(o: dict[str, Any]) -> str:
    cc = o.get("code", {})
    if isinstance(cc, dict):
        text = cc.get("text")
        if text:
            return str(text)
        coding = cc.get("coding", [])
        if coding and isinstance(coding[0], dict):
            return str(coding[0].get("display") or "Unknown observation")
    return "Unknown observation"


def _obs_line(o: dict[str, Any]) -> str:
    name = _obs_name(o)
    value = ""
    vu = o.get("valueQuantity", {})
    if isinstance(vu, dict) and "value" in vu:
        value = f"{vu.get('value')} {vu.get('unit', '')}".strip()
    elif "valueString" in o:
        value = str(o.get("valueString"))
    elif "valueCodeableConcept" in o and isinstance(o["valueCodeableConcept"], dict):
        value = str(o["valueCodeableConcept"].get("text", ""))

    interp = ""
    interps = o.get("interpretation", [])
    if interps and isinstance(interps[0], dict):
        coding = interps[0].get("coding", [])
        if coding and isinstance(coding[0], dict):
            interp = str(coding[0].get("display") or coding[0].get("code") or "")

    dt = str(o.get("effectiveDateTime") or o.get("issued") or "")
    parts = [p for p in [name, value, interp, dt] if p]
    return " | ".join(parts)


def build_fhir_patient_context(selection: dict, patient_id: str = "") -> str:
    resources = selection.get("needed_fhir_resources", []) or []
    intent = selection.get("intent", "general_or_unclear")

    if not resources:
        return "No patient specific FHIR context was selected for this request."

    requested = [str(r) for r in resources]
    counts = {r: 0 for r in requested}
    missing_categories: list[str] = []
    configured = _is_fhir_configured()
    patient_id = (patient_id or "").strip() or "unspecified-patient"

    # TODO: For future multi-patient support, replace static patient id with request-level patient identity.
    patient = _fhir_get_json(f"Patient/{patient_id}") if "Patient" in requested else None
    meds_bundle = _fhir_get_json("MedicationStatement", params={"subject": f"Patient/{patient_id}"}) if "MedicationStatement" in requested else None
    allergy_bundle = _fhir_get_json("AllergyIntolerance", params={"patient": patient_id}) if "AllergyIntolerance" in requested else None
    cond_bundle = _fhir_get_json("Condition", params={"subject": f"Patient/{patient_id}"}) if "Condition" in requested else None
    obs_bundle = _fhir_get_json("Observation", params={"subject": f"Patient/{patient_id}"}) if "Observation" in requested else None

    meds = _bundle_entries(meds_bundle)
    allergies = _bundle_entries(allergy_bundle)
    conditions = _bundle_entries(cond_bundle)
    observations = _bundle_entries(obs_bundle)

    if patient:
        counts["Patient"] = 1
    if "MedicationStatement" in counts:
        counts["MedicationStatement"] = len(meds)
    if "AllergyIntolerance" in counts:
        counts["AllergyIntolerance"] = len(allergies)
    if "Condition" in counts:
        counts["Condition"] = len(conditions)
    if "Observation" in counts:
        counts["Observation"] = len(observations)

    name = _human_name(patient or {})
    gender = str((patient or {}).get("gender") or "unknown")
    age = _compute_age((patient or {}).get("birthDate"))

    lines = [
        "FHIR PATIENT CONTEXT USED:",
        "Source: Google Cloud Healthcare API FHIR store",
        f"Patient: {name}",
        f"Patient ID: {patient_id}",
        "Note: This is selected FHIR context, not the full EHR.",
        "",
        "Age:",
        f"- {age}",
        "",
        "Gender:",
        f"- {gender}",
        "",
        "Active medications:",
    ]

    if meds:
        for m in meds[:20]:
            lines.append(f"- {_med_name(m)}")
    else:
        lines.append("- No active medications available from selected FHIR context.")
        missing_categories.append("active_medications")

    lines += ["", "Allergies:"]
    if allergies:
        for a in allergies[:20]:
            lines.append(f"- {_allergy_name(a)}")
    else:
        lines.append("- No allergies available from selected FHIR context.")
        missing_categories.append("allergies")

    lines += ["", "Active conditions:"]
    if conditions:
        for c in conditions[:20]:
            lines.append(f"- {_condition_name(c)}")
    else:
        lines.append("- No active conditions available from selected FHIR context.")
        missing_categories.append("active_conditions")

    lines += ["", "Relevant observations/labs:"]
    if observations:
        for o in observations[:30]:
            lines.append(f"- {_obs_line(o)}")
    else:
        lines.append("- No relevant observations/labs available from selected FHIR context.")
        missing_categories.append("relevant_labs")

    lines += [
        "",
        "Missing data notes:",
        "- Missing categories are explicitly noted; do not invent missing clinical facts.",
        "- If FHIR environment configuration is incomplete, treat this as unverified context.",
        "",
        "FHIR CONTEXT STATUS:",
        f"- fhir_configured: {configured}",
        f"- intent: {intent}",
        f"- resources_requested: {requested}",
        f"- resources_retrieved_counts: {counts}",
        f"- missing_categories: {missing_categories}",
    ]

    context = "\n".join(lines)
    logger.info(
        "fhir_context intent=%s requested=%s counts=%s context_len=%d",
        intent,
        requested,
        counts,
        len(context),
    )
    return context
