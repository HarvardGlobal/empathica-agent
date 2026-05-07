from __future__ import annotations

from typing import Optional


_MEDICATION_KEYWORDS = {
    "can i take",
    "is it safe",
    "medication safety",
    "drug interaction",
    "drug interactions",
    "side effect",
    "side effects",
    "contraindication",
    "contraindications",
    "dose",
    "dosing",
    "painkiller",
    "nsaid",
    "ibuprofen",
    "acetaminophen",
    "paracetamol",
    "aspirin",
}

_LAB_KEYWORDS = {
    "lab",
    "labs",
    "blood work",
    "wbc",
    "neutrophils",
    "hemoglobin",
    "platelets",
    "creatinine",
    "ast",
    "alt",
    "albumin",
    "ca 15-3",
    "cea",
    "vitamin d",
    "tsh",
}

_TREATMENT_KEYWORDS = {
    "chemotherapy",
    "chemo",
    "surgery",
    "radiation",
    "brca1",
    "recurrence",
    "fertility preservation",
    "oncology plan",
    "appointment",
    "upcoming appointments",
}

_EMOTION_KEYWORDS = {
    "anxiety",
    "anxious",
    "coping",
    "support",
    "communication preferences",
    "understanding medical information",
    "chemo brain",
    "technology challenges",
    "emotional",
}

_FINANCIAL_KEYWORDS = {
    "cost",
    "insurance",
    "pharmacy",
    "copay",
    "refill",
    "prior authorization",
    "access",
    "financial assistance",
}

_GENERAL_EDUCATION_PREFIXES = (
    "what is ",
    "how does ",
    "explain ",
)


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(k in text for k in keywords)


def _extract_query_terms(text: str, candidates: set[str], extras: list[str]) -> list[str]:
    terms = [c for c in sorted(candidates) if c in text]
    seen = set(terms)
    for extra in extras:
        if extra not in seen:
            terms.append(extra)
            seen.add(extra)
    return terms


def select_patient_document_needs(message: str, intent: Optional[str] = None) -> dict:
    text = (message or "").strip().lower()

    if not text:
        return {
            "needed_document_types": [],
            "query_terms": [],
            "reason": "Empty message; no patient-specific document retrieval selected.",
        }

    if intent == "general_education" or (
        any(text.startswith(p) for p in _GENERAL_EDUCATION_PREFIXES)
        and " my " not in f" {text} "
        and " i " not in f" {text} "
        and " can i " not in f" {text} "
    ):
        return {
            "needed_document_types": [],
            "query_terms": [],
            "reason": "General education request without patient-specific personalization.",
        }

    if _contains_any(text, _MEDICATION_KEYWORDS):
        return {
            "needed_document_types": ["medication_management", "oncology_notes", "care_coordination"],
            "query_terms": _extract_query_terms(
                text,
                _MEDICATION_KEYWORDS,
                ["medication", "side effects", "oncology", "pharmacy", "chemotherapy"],
            ),
            "reason": "Medication safety question; medication and oncology care notes may provide relevant patient-specific context.",
        }

    if _contains_any(text, _LAB_KEYWORDS):
        return {
            "needed_document_types": ["oncology_notes"],
            "query_terms": _extract_query_terms(text, _LAB_KEYWORDS, ["lab", "blood work", "monitoring"]),
            "reason": "Lab interpretation question; oncology notes likely include test trends and clinical interpretation.",
        }

    if _contains_any(text, _TREATMENT_KEYWORDS):
        return {
            "needed_document_types": ["oncology_notes", "care_coordination", "appointment_summaries"],
            "query_terms": _extract_query_terms(text, _TREATMENT_KEYWORDS, ["treatment", "oncology", "plan"]),
            "reason": "Treatment planning question; oncology and care coordination documents may contain relevant details.",
        }

    if _contains_any(text, _EMOTION_KEYWORDS):
        return {
            "needed_document_types": ["communication_preferences", "symptom_journal", "care_coordination"],
            "query_terms": _extract_query_terms(text, _EMOTION_KEYWORDS, ["support", "communication", "coping"]),
            "reason": "Emotional support or communication question; preference and support notes may be relevant.",
        }

    if _contains_any(text, _FINANCIAL_KEYWORDS):
        return {
            "needed_document_types": ["financial_access", "medication_management", "care_coordination"],
            "query_terms": _extract_query_terms(text, _FINANCIAL_KEYWORDS, ["cost", "access", "pharmacy"]),
            "reason": "Financial/access question; pharmacy and care coordination notes may contain practical support details.",
        }

    return {
        "needed_document_types": [],
        "query_terms": [],
        "reason": "No clear patient-specific unstructured document need detected.",
    }
