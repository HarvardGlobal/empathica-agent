"""
Tool: retrieve_literature
=========================
Retrieves relevant medical literature passages or evidence summaries for a
clinical query using semantic / vector search.
"""

import os
import logging

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("LITERATURE_RETRIEVAL_API_URL", "")


def build_evidence_context(evidence: str | None) -> str:
    """Return a labeled evidence block without inventing sources."""
    if evidence and evidence.strip():
        return f"Evidence/literature context provided:\n{evidence.strip()}"
    return "No evidence/literature context provided."


def retrieve_literature(query: str, max_results: int = 5) -> dict:
    if not _API_URL:
        logger.warning("retrieve_literature: LITERATURE_RETRIEVAL_API_URL not set — returning stub")
        return {
            "status": "unavailable",
            "query": query,
            "passages": [],
            "message": (
                "Literature retrieval service is not yet connected. "
                "Set LITERATURE_RETRIEVAL_API_URL in your environment. "
                "Do NOT fabricate citations. Answer from general knowledge "
                "and note that supporting literature was not retrieved."
            ),
        }

    try:
        import httpx

        response = httpx.post(
            f"{_API_URL.rstrip('/')}/retrieval/query",
            json={"query": query, "max_results": max_results},
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
        data["status"] = "ok"
        data["query"] = query
        return data
    except Exception as exc:
        logger.error("retrieve_literature: request failed for %r: %s", query, exc)
        return {
            "status": "error",
            "query": query,
            "passages": [],
            "message": (
                f"Literature retrieval failed: {exc}. "
                "Do not fabricate citations — note unavailability in your response."
            ),
        }
