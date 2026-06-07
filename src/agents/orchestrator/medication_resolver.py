from __future__ import annotations

import re
from dataclasses import dataclass, field

_BRAND_TO_GENERIC = {
    "tylenol": "acetaminophen",
    "advil": "ibuprofen",
    "motrin": "ibuprofen",
    "zofran": "ondansetron",
    "neupogen": "filgrastim",
    "taxol": "paclitaxel",
    "cytoxan": "cyclophosphamide",
    "adriamycin": "doxorubicin",
}

_FORM_WORDS = {
    "tablet", "tablets", "capsule", "capsules", "oral", "injection", "solution",
    "suspension", "cream", "gel", "patch", "spray", "mg", "mcg", "g", "ml", "unit", "units",
    "once", "daily", "twice", "three", "four", "daily", "weekly", "route",
}


@dataclass
class MedicationLookupResolution:
    input_medication: str
    lookup_candidates: list[str] = field(default_factory=list)
    preferred_candidate: str = ""
    identifier_used: str = "unknown"
    confidence: str = "low"
    warnings: list[str] = field(default_factory=list)


def _clean_name(text: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    filtered = [t for t in tokens if t not in _FORM_WORDS and not re.fullmatch(r"\d+(\.\d+)?", t)]
    return " ".join(filtered).strip()


def resolve_medication_name(medication: str, rxnorm_code: str | None = None, ndc: str | None = None, set_id: str | None = None) -> MedicationLookupResolution:
    raw = (medication or "").strip()
    cleaned = _clean_name(raw)
    candidates: list[str] = []
    warnings: list[str] = []
    identifier_used = "unknown"
    confidence = "low"

    if set_id:
        identifier_used = "set_id"
        candidates.append(set_id.strip())
        confidence = "high"
    elif ndc:
        identifier_used = "ndc"
        candidates.append(ndc.strip())
        confidence = "high"
    elif rxnorm_code:
        identifier_used = "rxcui"
        candidates.append(rxnorm_code.strip())
        confidence = "medium"

    if cleaned:
        generic = _BRAND_TO_GENERIC.get(cleaned.split()[0], cleaned)
        if generic and generic not in candidates:
            candidates.append(generic)
        if cleaned not in candidates:
            candidates.append(cleaned)
        if raw and raw.lower() != cleaned:
            warnings.append(f"normalized '{raw}' to '{cleaned}'")
        if confidence == "low":
            confidence = "medium" if generic != cleaned else "low"
    elif raw:
        candidates.append(raw.lower())
        warnings.append("medication name could not be normalized; using raw text")

    preferred = candidates[0] if candidates else ""
    return MedicationLookupResolution(
        input_medication=raw,
        lookup_candidates=list(dict.fromkeys(candidates)),
        preferred_candidate=preferred,
        identifier_used=identifier_used,
        confidence=confidence if preferred else "low",
        warnings=warnings,
    )


def normalize_free_text_medication(text: str) -> str:
    return _clean_name(text)
