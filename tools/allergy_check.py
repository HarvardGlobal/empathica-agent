"""
Tool: check_allergies
=====================
Checks whether a named drug (or drug class) conflicts with the patient's
recorded allergy list.

Backend expectation
-------------------
Wire PATIENT_CONTEXT_API_URL (or a dedicated allergy-check endpoint) in
.env.example.  Until wired, the tool returns a graceful stub.

Safety note
-----------
If this tool returns status="unavailable", the orchestrator MUST surface that
allergy status could not be verified and recommend the patient check with their
pharmacist or prescriber before taking the medication.  Never assume no allergy
exists simply because the tool could not confirm one.
"""

import os
import logging

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("PATIENT_CONTEXT_API_URL", "")


def check_allergies(patient_id: str, drug_name: str) -> dict:
    """
    Check whether a patient has a recorded allergy to a drug or drug class.

    Parameters
    ----------
    patient_id : str
        The unique patient identifier.
    drug_name : str
        The drug or drug-class name to check against the patient's allergy list.

    Returns
    -------
    dict
        Keys: status, patient_id, drug_name, allergy_found (bool),
              allergy_details, severity, recommendation.
        On failure or missing backend: status="unavailable" with a message.
    """
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
