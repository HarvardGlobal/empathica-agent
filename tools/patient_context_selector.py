"""Deterministic patient context selector based on user message intent."""

from __future__ import annotations

import re


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def select_patient_context_needs(message: str) -> dict:
    """
    Select relevant patient context categories/FHIR resources from message only.

    This function is deterministic and intentionally does not inspect raw EHR/FHIR data.
    """
    text = (message or "").strip()
    lowered = text.lower()

    medication_safety_patterns = [
        r"\bcan i take\b",
        r"\bis it safe to take\b",
        r"\bwith my medication\b",
        r"\bwith warfarin\b",
        r"\bdrug interactions?\b",
        r"\bside effects?\b",
        r"\bcontraindications?\b",
        r"\bdosing\b",
        r"\bpainkiller\b",
        r"\bnsaid\b",
        r"\bibuprofen\b",
        r"\bacetaminophen\b",
        r"\bparacetamol\b",
        r"\baspirin\b",
        r"\bsafe\b",
    ]
    allergy_patterns = [
        r"\ballerg(y|ic|ies)\b",
        r"\bintolerance\b",
        r"\brash\b",
        r"\bhives\b",
        r"\banaphylaxis\b",
        r"\ballergic reaction\b",
    ]
    lab_patterns = [
        r"\blab(s)?\b",
        r"\bblood test(s)?\b",
        r"\bkidney function\b",
        r"\bliver function\b",
        r"\bcreatinine\b",
        r"\begfr\b",
        r"\bast\b",
        r"\balt\b",
        r"\binr\b",
        r"\bpotassium\b",
        r"\bsodium\b",
        r"\bhemoglobin\b",
        r"\bwbc\b",
        r"\bneutrophils?\b",
        r"\bplatelets?\b",
        r"\bca ?15-?3\b",
        r"\bcea\b",
        r"\bvitamin d\b",
        r"\btsh\b",
    ]

    general_education_patterns = [
        r"^what is\b",
        r"^how does\b",
        r"^what does\b",
    ]
    personalization_patterns = [
        r"\bcan i\b",
        r"\bfor me\b",
        r"\bmy\b",
        r"\bsafe\b",
        r"\bwith\b",
    ]
    if _contains_any(lowered, general_education_patterns) and not _contains_any(
        lowered, personalization_patterns
    ):
        return {
            "intent": "general_education",
            "needed_context_categories": [],
            "needed_fhir_resources": [],
            "reason": (
                "General education request detected; no patient-specific FHIR context is needed "
                "unless personalization is requested."
            ),
        }

    # Rule order: medication safety first for personalized safety questions,
    # then allergy-specific, then labs, then fallback.
    if _contains_any(lowered, medication_safety_patterns):
        return {
            "intent": "medication_safety",
            "needed_context_categories": [
                "age",
                "active_medications",
                "allergies",
                "active_conditions",
                "recent_kidney_function",
                "recent_liver_function_if_relevant",
                "recent_blood_counts_if_relevant",
            ],
            "needed_fhir_resources": [
                "Patient",
                "MedicationStatement",
                "AllergyIntolerance",
                "Condition",
                "Observation",
            ],
            "reason": (
                "Medication safety questions require checking current medications, allergies, "
                "active conditions, age, and relevant organ function context."
            ),
        }

    if _contains_any(lowered, allergy_patterns):
        return {
            "intent": "allergy_check",
            "needed_context_categories": [
                "allergies",
                "active_medications",
                "active_conditions",
            ],
            "needed_fhir_resources": [
                "AllergyIntolerance",
                "MedicationStatement",
                "Condition",
            ],
            "reason": (
                "Allergy-focused questions require allergy records plus current medications "
                "and conditions for context."
            ),
        }

    if _contains_any(lowered, lab_patterns):
        return {
            "intent": "lab_interpretation",
            "needed_context_categories": [
                "relevant_labs",
                "active_conditions",
                "active_medications",
            ],
            "needed_fhir_resources": [
                "Observation",
                "Condition",
                "MedicationStatement",
            ],
            "reason": (
                "Lab interpretation needs relevant labs plus condition and medication context."
            ),
        }

    return {
        "intent": "general_or_unclear",
        "needed_context_categories": [],
        "needed_fhir_resources": [],
        "reason": (
            "The message does not clearly require patient-specific context, or intent is mixed/unclear."
        ),
    }
