from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.ingestion.parser import ParsedLabel
from app.services.utils.matching import normalize_drug_name


@dataclass
class NormalizedLabel:
    set_id: str
    spl_id: str
    generic_name: str
    normalized_generic_name: str
    brand_names: list[str] = field(default_factory=list)
    manufacturer: str = ""
    labeler: str = ""
    active_ingredients: list[str] = field(default_factory=list)
    drug_classes: list[str] = field(default_factory=list)
    dosage_forms: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    source_url: str = ""
    source_system: str = ""

    # Derived structured fact fields
    plain_language_purpose: str = ""
    common_side_effects: list[str] = field(default_factory=list)
    boxed_warning_flag: bool = False


class LabelNormalizer:
    """Normalizes a ParsedLabel into a NormalizedLabel ready for DB insertion."""

    MAX_PURPOSE_CHARS = 200
    MAX_SIDE_EFFECTS = 10

    def normalize(self, parsed: ParsedLabel) -> NormalizedLabel:
        """
        Normalize a parsed label:
        - Normalize drug name
        - Deduplicate and strip empty strings from list fields
        - Derive plain_language_purpose from indications section
        - Extract common_side_effects from adverse_reactions section
        - Set boxed_warning_flag
        """
        generic_name = (parsed.generic_name or "").strip()
        normalized_generic = normalize_drug_name(generic_name)

        brand_names = _dedupe_nonempty(parsed.brand_names)
        active_ingredients = _dedupe_nonempty(parsed.active_ingredients)
        drug_classes = _dedupe_nonempty(parsed.drug_classes)
        dosage_forms = _dedupe_nonempty(parsed.dosage_forms)
        routes = _dedupe_nonempty(parsed.routes)

        # Strip empty section values
        sections = {k: v for k, v in (parsed.sections or {}).items() if v and v.strip()}

        # Derive plain_language_purpose
        indications_text = sections.get("indications_and_usage", "")
        plain_language_purpose = _extract_purpose(indications_text, self.MAX_PURPOSE_CHARS)

        # Extract common side effects
        adverse_text = sections.get("adverse_reactions", "")
        common_side_effects = _extract_side_effects(adverse_text, self.MAX_SIDE_EFFECTS)

        # Boxed warning flag
        boxed_warning_text = sections.get("boxed_warning", "")
        boxed_warning_flag = bool(boxed_warning_text and boxed_warning_text.strip())

        return NormalizedLabel(
            set_id=parsed.set_id,
            spl_id=parsed.spl_id,
            generic_name=generic_name,
            normalized_generic_name=normalized_generic,
            brand_names=brand_names,
            manufacturer=parsed.manufacturer or "",
            labeler=parsed.labeler or "",
            active_ingredients=active_ingredients,
            drug_classes=drug_classes,
            dosage_forms=dosage_forms,
            routes=routes,
            sections=sections,
            source_url=parsed.source_url or "",
            source_system=parsed.source_system or "",
            plain_language_purpose=plain_language_purpose,
            common_side_effects=common_side_effects,
            boxed_warning_flag=boxed_warning_flag,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _dedupe_nonempty(items: list[str]) -> list[str]:
    """Deduplicate while preserving order; strip empty strings."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items or []:
        cleaned = (item or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _extract_purpose(text: str, max_chars: int) -> str:
    """Extract a short plain-language purpose from indications text."""
    if not text or not text.strip():
        return ""
    # Take the first sentence or first max_chars chars
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    truncated = stripped[:max_chars]
    # Try to end at a word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]
    return truncated + "..."


def _extract_side_effects(text: str, max_items: int) -> list[str]:
    """
    Extract common side effect keywords from adverse_reactions text.
    Splits on semicolons and commas, returns up to max_items cleaned items.
    """
    if not text or not text.strip():
        return []

    # Remove parenthetical notes and numbers
    cleaned = re.sub(r"\([^)]*\)", "", text)
    cleaned = re.sub(r"\d+[\d.,]*\s*%", "", cleaned)

    # Split on semicolons and commas
    raw_items = re.split(r"[;,]", cleaned)

    effects: list[str] = []
    for item in raw_items:
        item = item.strip()
        # Filter out items that are too long (likely sentences, not keywords)
        if item and len(item.split()) <= 5:
            # Capitalize first letter
            normalized = item.capitalize()
            if normalized not in effects:
                effects.append(normalized)
        if len(effects) >= max_items:
            break

    return effects
