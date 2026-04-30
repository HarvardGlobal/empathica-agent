from __future__ import annotations

import difflib
import re
import string
from typing import Optional


def normalize_drug_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    name = name.lower()
    # Remove punctuation characters
    name = name.translate(str.maketrans("", "", string.punctuation))
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def fuzzy_score(a: str, b: str) -> float:
    """Return a 0.0-1.0 similarity score using difflib.SequenceMatcher."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def find_best_match(
    query: str,
    candidates: list[str],
    threshold: float = 0.8,
) -> Optional[tuple[str, float]]:
    """
    Find the best fuzzy match from candidates for query.

    Returns (best_candidate, score) if score >= threshold, else None.
    Operates on the raw candidate strings; normalize before calling if needed.
    """
    if not candidates:
        return None

    best_candidate: Optional[str] = None
    best_score: float = 0.0

    for candidate in candidates:
        score = fuzzy_score(query, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_score >= threshold and best_candidate is not None:
        return best_candidate, best_score

    return None
