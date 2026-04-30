"""
Tool: drug_lookup
=================
Retrieves structured drug information (purpose, dosing, side effects,
contraindications, warnings) for a named medication.

Backend expectation
-------------------
Wire DRUG_KNOWLEDGE_API_URL (see .env.example) to the drug knowledge service
(e.g. the FastAPI + DailyMed/openFDA ingestion pipeline).  Until wired, the
tool returns a graceful stub so the orchestrator can degrade cleanly.

Safety note
-----------
This tool returns factual drug-label data only.  Clinical interpretation,
dose recommendations, and patient-specific advice must remain in the
orchestrator's reasoning layer — never inside this tool.
"""

import os
import logging

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("DRUG_KNOWLEDGE_API_URL", "")


def drug_lookup(drug_name: str) -> dict:
    """
    Look up structured information for a named drug.

    Parameters
    ----------
    drug_name : str
        The name of the medication to look up (brand or generic).

    Returns
    -------
    dict
        Keys: status, drug_name, purpose, side_effects, contraindications,
              warnings, dosing_notes, source.
        On failure or missing backend: status="unavailable" with a message.
    """
    if not _API_URL:
        logger.warning("drug_lookup: DRUG_KNOWLEDGE_API_URL not set — returning stub response")
        return {
            "status": "unavailable",
            "drug_name": drug_name,
            "message": (
                "Drug knowledge service is not yet connected. "
                "Set DRUG_KNOWLEDGE_API_URL in your environment to enable live lookups. "
                "The orchestrator should answer from general knowledge while noting "
                "that specific label data could not be retrieved."
            ),
        }

    try:
        import httpx
        response = httpx.get(
            f"{_API_URL.rstrip('/')}/drugs/lookup",
            params={"name": drug_name},
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        data["status"] = "ok"
        return data
    except Exception as exc:
        logger.error("drug_lookup: request failed for %r: %s", drug_name, exc)
        return {
            "status": "error",
            "drug_name": drug_name,
            "message": f"Drug lookup failed: {exc}. Use general knowledge with appropriate uncertainty.",
        }
