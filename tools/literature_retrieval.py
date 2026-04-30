"""
Tool: retrieve_literature
=========================
Retrieves relevant medical literature passages or evidence summaries for a
clinical query using semantic / vector search.

Backend expectation
-------------------
Wire LITERATURE_RETRIEVAL_API_URL (see .env.example) to your vector store or
RAG retrieval service.  Until wired, the tool returns a graceful stub.

Safety note
-----------
Retrieved passages must be cited as the source of any evidence claim.  If this
tool returns status="unavailable", the orchestrator must not fabricate citations
or imply evidence-based support it cannot substantiate.  State clearly that
literature retrieval was unavailable.
"""

import os
import logging

logger = logging.getLogger(__name__)

_API_URL = os.environ.get("LITERATURE_RETRIEVAL_API_URL", "")


def retrieve_literature(query: str, max_results: int = 5) -> dict:
    """
    Retrieve relevant medical literature passages for a clinical query.

    Parameters
    ----------
    query : str
        The clinical question or topic to search for.
    max_results : int
        Maximum number of passages to return (default 5).

    Returns
    -------
    dict
        Keys: status, query, passages (list of dicts with text, source, score).
        On failure or missing backend: status="unavailable" with a message.
    """
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
