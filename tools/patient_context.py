"""
Tool: get_patient_context
=========================
Retrieves the current patient's medical context: active medications, known
diagnoses, demographic data (age, weight), and any relevant clinical notes.

Backend expectation
-------------------
Wire PATIENT_CONTEXT_API_URL (see .env.example) to your EHR integration or
patient data service.  Until wired, the tool returns a graceful stub.

Safety note
-----------
NEVER hallucinate patient data.  If this tool returns status="unavailable",
the orchestrator MUST NOT assume or invent any patient-specific facts.
It should explicitly state that patient-specific information is not available
and recommend the patient consult their healthcare provider.
"""

import os
import logging

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("PATIENT_CONTEXT_API_URL", "")


def get_patient_context(patient_id: str) -> dict:
    """
    Retrieve the medical context for a patient by ID.

    Parameters
    ----------
    patient_id : str
        The unique identifier for the patient in the patient data system.

    Returns
    -------
    dict
        Keys: status, patient_id, medications, diagnoses, age, allergies,
              clinical_notes.
        On failure or missing backend: status="unavailable" with a message.
    """
    if not _API_URL:
        logger.warning("get_patient_context: PATIENT_CONTEXT_API_URL not set — returning stub")
        return {
            "status": "unavailable",
            "patient_id": patient_id,
            "message": (
                "Patient context service is not yet connected. "
                "Set PATIENT_CONTEXT_API_URL in your environment. "
                "Do NOT assume or invent patient-specific data. "
                "Answer in general terms only and advise the patient to consult "
                "their healthcare provider for personalised advice."
            ),
        }

    try:
        import httpx
        response = httpx.get(
            f"{_API_URL.rstrip('/')}/patients/{patient_id}/context",
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        data["status"] = "ok"
        return data
    except Exception as exc:
        logger.error("get_patient_context: request failed for %r: %s", patient_id, exc)
        return {
            "status": "error",
            "patient_id": patient_id,
            "message": (
                f"Patient context retrieval failed: {exc}. "
                "Do NOT invent patient data. Answer in general terms only."
            ),
        }
