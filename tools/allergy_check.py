"""
Tool: check_allergies
=====================
Checks whether a named drug (or drug class) conflicts with the patient's
recorded allergy list.
"""

import os
import logging
import re

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("PATIENT_CONTEXT_API_URL", "")


def build_allergy_context(patient_context: str | None, dailymed_context: str | None) -> str:
    """Build conservative allergy context from provided text only."""
    pc = (patient_context or "").strip()
    dc = (dailymed_context or "").strip()
    text = f"{pc}\n{dc}".lower()

    found = []
    if re.search(r"\ballerg(y|ic|ies)\b", text):
        found.append("Allergy-related terms were present in provided context.")
    if "anaphylaxis" in text:
        found.append("Anaphylaxis mention detected in provided context.")
    if "contraindication" in text and "allerg" in text:
        found.append("Potential allergy-related contraindication mention in label context.")

    if found:
        return "Allergy context:\n- " + "\n- ".join(found)
    return "No explicit allergy conflict was identified from the provided context."


def check_allergies(patient_id: str, drug_name: str) -> dict:
    if not _API_URL:
        logger.warning("check_allergies: PATIENT_CONTEXT_API_URL not set — returning stub")
        return {
            "status": "unavailable",
            "patient_id": patient_id,
            "drug_name": drug_name,
            "message": (
                "Allergy check service is not yet connected. "
                "Set PATIENT_CONTEXT_API_URL in your environment. "
                "IMPORTANT: you cannot confirm or deny a drug allergy. "
                "Advise the patient to verify their allergy status with their "
                "pharmacist or prescriber before taking the medication."
            ),
        }

    try:
        import httpx

        response = httpx.get(
            f"{_API_URL.rstrip('/')}/patients/{patient_id}/allergies/check",
            params={"drug": drug_name},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        data["status"] = "ok"
        return data
    except Exception as exc:
        logger.error("check_allergies: request failed (%r, %r): %s", patient_id, drug_name, exc)
        return {
            "status": "error",
            "patient_id": patient_id,
            "drug_name": drug_name,
            "message": (
                f"Allergy check failed: {exc}. "
                "Cannot confirm allergy status — advise patient to verify with their pharmacist."
            ),
        }
