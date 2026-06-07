from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any

import google.auth
from google.auth.transport.requests import Request
import httpx

from .context_catalog import CONTEXT_CATALOG
from .retrieval_plan_schema import RetrievalPlan
from ...tools.documents.patient_document_rag import retrieve_patient_document_context

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
        logger.warning("fhir_auth_unavailable reason=%s", type(exc).__name__)
        return ""


def _is_configured() -> bool:
    return all([FHIR_PROJECT_ID, FHIR_LOCATION, FHIR_DATASET, FHIR_STORE])


def _get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    token = _auth_token()
    if not token:
        return None
    url = f"{_fhir_base()}/{path.lstrip('/')}"
    try:
        response = httpx.get(url, params=params, headers={"Authorization": f"Bearer {token}", "Accept": "application/fhir+json"}, timeout=12.0)
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
        resource = entry.get("resource") if isinstance(entry, dict) else None
        if isinstance(resource, dict):
            out.append(resource)
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


def _observation_matches(obs: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    text = " ".join(
        str(part).lower()
        for part in [
            obs.get("code", {}).get("text", "") if isinstance(obs.get("code"), dict) else "",
            obs.get("code", {}).get("coding", [{}])[0].get("display", "") if isinstance(obs.get("code"), dict) else "",
        ]
    )
    return _observation_score(obs, keywords) > 0


def _observation_score(obs: dict[str, Any], keywords: tuple[str, ...]) -> int:
    text = " ".join(
        str(part).lower()
        for part in [
            obs.get("code", {}).get("text", "") if isinstance(obs.get("code"), dict) else "",
            obs.get("code", {}).get("coding", [{}])[0].get("display", "") if isinstance(obs.get("code"), dict) else "",
        ]
    )
    score = 0
    for keyword in keywords:
        term = keyword.lower().strip()
        if not term:
            continue
        if term in text:
            score += 3 if " " in term else 2
        if term and term.replace(" ", "") in text.replace(" ", ""):
            score += 1
    if any(token in text for token in ("blood pressure", "heart rate", "pulse", "ast", "alt", "alp", "bilirubin", "albumin")):
        score += 1
    return score


def _obs_line(obs: dict[str, Any]) -> dict[str, Any]:
    name = ""
    code = obs.get("code", {})
    if isinstance(code, dict):
        name = str(code.get("text") or "")
        coding = code.get("coding", [])
        if not name and coding and isinstance(coding[0], dict):
            name = str(coding[0].get("display") or "")
    if not name:
        name = "Unknown observation"
    value = None
    unit = ""
    if isinstance(obs.get("valueQuantity"), dict):
        value = obs["valueQuantity"].get("value")
        unit = str(obs["valueQuantity"].get("unit") or "")
    elif "valueString" in obs:
        value = obs.get("valueString")
    date_value = str(obs.get("effectiveDateTime") or obs.get("issued") or "")
    return {"name": name, "value": value, "unit": unit, "date": date_value}


def _fetch_observation_domain(patient_id: str, keywords: tuple[str, ...], lookback_days: int | None) -> dict:
    bundle = _get_json("Observation", params={"subject": f"Patient/{patient_id}"})
    scored = [(_observation_score(obs, keywords), obs) for obs in _entries(bundle)]
    observations = [obs for score, obs in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0]
    if not observations:
        return {
            "status": "unavailable",
            "source_resources": ["Observation"],
            "summary": f"No matching observations were found for {', '.join(keywords)}.",
            "structured_items": [],
            "most_recent_date": None,
            "missing_details": ["No matching observations were found."],
            "confidence": "low",
        }
    structured = [_obs_line(obs) for obs in observations[:10]]
    most_recent = max((item.get("date") or "" for item in structured), default="")
    summary = f"Most recent matching observation is {structured[0]['name']}"
    if structured[0].get("value") is not None:
        summary += f" = {structured[0]['value']} {structured[0].get('unit', '')}".rstrip()
    summary += f" from {structured[0].get('date') or 'unknown date'}."
    return {
        "status": "available",
        "source_resources": ["Observation"],
        "summary": summary,
        "structured_items": structured,
        "most_recent_date": most_recent or None,
        "missing_details": [],
        "confidence": "high",
    }


def execute_retrieval_plan(
    plan: RetrievalPlan,
    *,
    fhir_patient_id: str,
    document_patient_id: str,
    docs_prefix: str = "",
    user_message: str = "",
) -> dict:
    if not plan.requires_patient_specific_context and plan.intent == "general_education":
        return {
            "configured": _is_configured(),
            "domains": {},
            "warnings": [],
            "missing_context": [],
            "source_trace": [],
        }

    domains = [item.domain for item in plan.required_context + plan.optional_context]
    domains = list(dict.fromkeys(domains))
    results: dict[str, dict] = {}
    warnings: list[str] = []
    source_trace: list[dict[str, Any]] = []
    missing_context: list[str] = []

    if not domains:
        return {
            "configured": _is_configured(),
            "domains": {},
            "warnings": ["No domains selected for retrieval."],
            "missing_context": [],
            "source_trace": [],
        }

    patient = _get_json(f"Patient/{fhir_patient_id}") if "demographics" in domains else None
    if patient is not None:
        name = _human_name(patient)
        results["demographics"] = {
            "status": "available",
            "source_resources": ["Patient"],
            "summary": f"Patient name is {name} and age is {_compute_age(patient.get('birthDate'))}.",
            "structured_items": [{
                "name": name,
                "age": _compute_age(patient.get("birthDate")),
                "gender": patient.get("gender", "unknown"),
                "birthDate": patient.get("birthDate"),
            }],
            "most_recent_date": None,
            "missing_details": [],
            "confidence": "high",
        }
        source_trace.append({"domain": "demographics", "resource": "Patient", "status": "available"})
    elif "demographics" in domains:
        results["demographics"] = {
            "status": "unavailable",
            "source_resources": ["Patient"],
            "summary": "No patient demographics were available.",
            "structured_items": [],
            "most_recent_date": None,
            "missing_details": ["Patient resource unavailable."],
            "confidence": "low",
        }
        missing_context.append("demographics")

    if "active_medications" in domains:
        bundle = _get_json("MedicationStatement", params={"subject": f"Patient/{fhir_patient_id}"})
        meds = _entries(bundle)
        items = []
        for med in meds[:15]:
            cc = med.get("medicationCodeableConcept", {}) if isinstance(med, dict) else {}
            name = "Unknown medication"
            if isinstance(cc, dict):
                name = str(cc.get("text") or "")
                if not name:
                    coding = cc.get("coding", [])
                    if coding and isinstance(coding[0], dict):
                        name = str(coding[0].get("display") or name)
            items.append({"name": name or "Unknown medication", "status": med.get("status", "") if isinstance(med, dict) else "", "date": med.get("effectiveDateTime") if isinstance(med, dict) else ""})
        if items:
            results["active_medications"] = {
                "status": "available",
                "source_resources": ["MedicationStatement"],
                "summary": f"{len(items)} active medication statements were found.",
                "structured_items": items,
                "most_recent_date": max((item.get("date") or "" for item in items), default="") or None,
                "missing_details": [],
                "confidence": "high",
            }
        else:
            results["active_medications"] = {
                "status": "unavailable",
                "source_resources": ["MedicationStatement"],
                "summary": "No active medication statements were found.",
                "structured_items": [],
                "most_recent_date": None,
                "missing_details": ["No active medications found."],
                "confidence": "low",
            }
            missing_context.append("active_medications")
        source_trace.append({"domain": "active_medications", "resource": "MedicationStatement", "status": results["active_medications"]["status"]})

    if "allergies" in domains:
        bundle = _get_json("AllergyIntolerance", params={"patient": fhir_patient_id})
        allergies = _entries(bundle)
        items = []
        for allergy in allergies[:15]:
            code = allergy.get("code", {}) if isinstance(allergy, dict) else {}
            name = "Unknown allergy"
            if isinstance(code, dict):
                name = str(code.get("text") or "")
                if not name:
                    coding = code.get("coding", [])
                    if coding and isinstance(coding[0], dict):
                        name = str(coding[0].get("display") or name)
            items.append({"name": name or "Unknown allergy", "reaction": allergy.get("reaction", []) if isinstance(allergy, dict) else [], "date": allergy.get("recordedDate") if isinstance(allergy, dict) else ""})
        if items:
            results["allergies"] = {
                "status": "available",
                "source_resources": ["AllergyIntolerance"],
                "summary": f"{len(items)} allergies/intolerances were found.",
                "structured_items": items,
                "most_recent_date": max((item.get("date") or "" for item in items), default="") or None,
                "missing_details": [],
                "confidence": "high",
            }
        else:
            results["allergies"] = {
                "status": "unavailable",
                "source_resources": ["AllergyIntolerance"],
                "summary": "No allergies were found in the selected FHIR context.",
                "structured_items": [],
                "most_recent_date": None,
                "missing_details": ["No AllergyIntolerance resources were available."],
                "confidence": "low",
            }
            missing_context.append("allergies")
        source_trace.append({"domain": "allergies", "resource": "AllergyIntolerance", "status": results["allergies"]["status"]})

    if "active_conditions" in domains:
        bundle = _get_json("Condition", params={"subject": f"Patient/{fhir_patient_id}"})
        conditions = _entries(bundle)
        items = []
        for condition in conditions[:20]:
            code = condition.get("code", {}) if isinstance(condition, dict) else {}
            name = "Unknown condition"
            if isinstance(code, dict):
                name = str(code.get("text") or "")
                if not name:
                    coding = code.get("coding", [])
                    if coding and isinstance(coding[0], dict):
                        name = str(coding[0].get("display") or name)
            items.append({"name": name or "Unknown condition", "date": condition.get("onsetDateTime") if isinstance(condition, dict) else ""})
        if items:
            results["active_conditions"] = {
                "status": "available",
                "source_resources": ["Condition"],
                "summary": f"{len(items)} active conditions were found.",
                "structured_items": items,
                "most_recent_date": max((item.get("date") or "" for item in items), default="") or None,
                "missing_details": [],
                "confidence": "high",
            }
        else:
            results["active_conditions"] = {
                "status": "unavailable",
                "source_resources": ["Condition"],
                "summary": "No active conditions were found.",
                "structured_items": [],
                "most_recent_date": None,
                "missing_details": ["No active conditions were available."],
                "confidence": "low",
            }
            missing_context.append("active_conditions")
        source_trace.append({"domain": "active_conditions", "resource": "Condition", "status": results["active_conditions"]["status"]})

    observation_domains = {
        "kidney_function": ("eGFR", "creatinine", "BUN", "renal", "kidney"),
        "liver_function": ("AST", "ALT", "ALP", "alkaline phosphatase", "bilirubin", "albumin", "liver", "hepatic"),
        "blood_counts": ("hemoglobin", "WBC", "white blood cells", "neutrophils", "platelets", "hematocrit"),
        "vital_signs": ("blood pressure", "systolic", "diastolic", "heart rate", "pulse", "temperature", "oxygen saturation", "respiratory rate"),
        "bleeding_risk_context": ("platelets", "anemia", "anticoagulant", "bleed", "ulcer"),
        "gi_risk_context": ("ulcer", "GI bleed", "stomach", "GERD", "gastritis", "NSAID"),
        "cardiovascular_risk_context": ("blood pressure", "systolic", "diastolic", "heart rate", "pulse", "cardiovascular", "stroke", "myocardial infarction", "mi", "arrhythmia"),
        "pregnancy_or_reproductive_context": ("pregnan", "breastfeeding", "lactation", "reproductive"),
        "recent_symptoms": ("pain", "fever", "shortness of breath", "nausea", "vomiting", "chest pain"),
    }
    for domain, keywords in observation_domains.items():
        if domain in domains:
            results[domain] = _fetch_observation_domain(fhir_patient_id, keywords, CONTEXT_CATALOG[domain]["default_lookback_days"])
            if results[domain]["status"] == "unavailable":
                missing_context.append(domain)
            source_trace.append({"domain": domain, "resource": "Observation", "status": results[domain]["status"]})

    if "unstructured_patient_notes" in domains:
        document_package = retrieve_patient_document_context(
            patient_id=document_patient_id,
            query=user_message,
            top_k=5,
            docs_prefix=docs_prefix or f"patients/{document_patient_id}/",
        )
        status = "available" if document_package.get("snippets") else document_package.get("status", "unavailable")
        results["unstructured_patient_notes"] = {
            "status": status,
            "source_resources": ["DocumentReference"],
            "summary": document_package.get("summary", "") or (
                "Patient document snippets were retrieved."
                if document_package.get("snippets")
                else "No relevant uploaded document snippet was found."
            ),
            "structured_items": document_package.get("snippets", []),
            "most_recent_date": None,
            "missing_details": document_package.get("missing_document_context", []),
            "confidence": "medium" if document_package.get("snippets") else "low",
            "document_rag_package": document_package,
        }
        warnings.extend(document_package.get("warnings", []) or [])
        if status in {"unavailable", "error"}:
            missing_context.append("unstructured_patient_notes")
        source_trace.append(
            {
                "domain": "unstructured_patient_notes",
                "resource": "DocumentReference",
                "status": results["unstructured_patient_notes"]["status"],
                "retrieval_method": document_package.get("retrieval_method", "none"),
            }
        )

    return {
        "configured": _is_configured(),
        "domains": results,
        "warnings": warnings,
        "missing_context": missing_context,
        "source_trace": source_trace,
    }
