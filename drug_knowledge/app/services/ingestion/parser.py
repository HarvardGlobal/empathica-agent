from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


CANONICAL_SECTION_TYPES: list[str] = [
    "boxed_warning",
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings_and_precautions",
    "adverse_reactions",
    "drug_interactions",
    "use_in_specific_populations",
    "clinical_pharmacology",
    "patient_counseling_information",
    "how_supplied",
    "storage_and_handling",
]

# Map raw section header strings to canonical section_type keys
SECTION_HEADER_MAP: dict[str, str] = {
    # Boxed warning
    "boxed warning": "boxed_warning",
    "black box warning": "boxed_warning",
    "warning": "boxed_warning",
    "warnings": "boxed_warning",
    # Indications
    "indications and usage": "indications_and_usage",
    "indications & usage": "indications_and_usage",
    "indications": "indications_and_usage",
    "indication": "indications_and_usage",
    # Dosage
    "dosage and administration": "dosage_and_administration",
    "dosage & administration": "dosage_and_administration",
    "dosage": "dosage_and_administration",
    "administration": "dosage_and_administration",
    # Contraindications
    "contraindications": "contraindications",
    "contraindication": "contraindications",
    # Warnings and precautions
    "warnings and precautions": "warnings_and_precautions",
    "warnings & precautions": "warnings_and_precautions",
    "precautions": "warnings_and_precautions",
    # Adverse reactions
    "adverse reactions": "adverse_reactions",
    "adverse events": "adverse_reactions",
    "side effects": "adverse_reactions",
    # Drug interactions
    "drug interactions": "drug_interactions",
    "interactions": "drug_interactions",
    # Special populations
    "use in specific populations": "use_in_specific_populations",
    "specific populations": "use_in_specific_populations",
    # Clinical pharmacology
    "clinical pharmacology": "clinical_pharmacology",
    "pharmacology": "clinical_pharmacology",
    # Patient counseling
    "patient counseling information": "patient_counseling_information",
    "patient counseling": "patient_counseling_information",
    "medication guide": "patient_counseling_information",
    # How supplied
    "how supplied": "how_supplied",
    "how supplied/storage and handling": "how_supplied",
    # Storage
    "storage and handling": "storage_and_handling",
    "storage": "storage_and_handling",
    "handling": "storage_and_handling",
}


def _map_section_header(header: str) -> Optional[str]:
    """Map a raw section header to a canonical section_type."""
    normalized = header.lower().strip()
    # Direct match
    if normalized in SECTION_HEADER_MAP:
        return SECTION_HEADER_MAP[normalized]
    # Partial match
    for key, canonical in SECTION_HEADER_MAP.items():
        if key in normalized or normalized in key:
            return canonical
    return None


@dataclass
class ParsedLabel:
    set_id: str
    spl_id: str
    generic_name: str
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


class LabelParser:
    """Parses raw API responses from DailyMed and openFDA into ParsedLabel objects."""

    def parse_dailymed_label(self, raw: dict[str, Any]) -> ParsedLabel:
        """Parse a raw DailyMed SPL response dict."""
        data = raw if "set_id" in raw else raw.get("data", raw)

        set_id = str(data.get("set_id", data.get("setid", "")))
        spl_id = str(data.get("spl_id", data.get("splid", "")))
        generic_name = str(data.get("generic_name", ""))

        brand_names: list[str] = []
        raw_brands = data.get("brand_names", data.get("brand_name", []))
        if isinstance(raw_brands, str) and raw_brands:
            brand_names = [raw_brands]
        elif isinstance(raw_brands, list):
            brand_names = [str(b) for b in raw_brands if b]

        manufacturer = str(data.get("manufacturer_name", data.get("manufacturer", "")))
        labeler = str(data.get("labeler_name", data.get("labeler", "")))

        active_ingredients: list[str] = []
        raw_ai = data.get("active_ingredients", [])
        if isinstance(raw_ai, list):
            for item in raw_ai:
                if isinstance(item, dict):
                    name = item.get("name", item.get("ingredient_name", ""))
                    if name:
                        active_ingredients.append(str(name))
                elif isinstance(item, str) and item:
                    active_ingredients.append(item)
        elif isinstance(raw_ai, str) and raw_ai:
            active_ingredients = [raw_ai]

        drug_classes: list[str] = _extract_list(data, "drug_class", "drug_classes", "pharm_class")
        dosage_forms: list[str] = _extract_list(data, "dosage_form", "dosage_forms")
        routes: list[str] = _extract_list(data, "route", "routes")

        # Parse sections from the 'sections' list or 'spl_sections' key
        sections: dict[str, str] = {}
        raw_sections = data.get("sections", data.get("spl_sections", []))
        if isinstance(raw_sections, list):
            for sec in raw_sections:
                if not isinstance(sec, dict):
                    continue
                header = str(sec.get("title", sec.get("section_type", "")))
                text = str(sec.get("text", sec.get("section_text", "")))
                if header and text:
                    canonical = _map_section_header(header)
                    if canonical:
                        sections[canonical] = text
        elif isinstance(raw_sections, dict):
            for header, text in raw_sections.items():
                canonical = _map_section_header(str(header))
                if canonical and text:
                    sections[canonical] = str(text)

        source_url = str(
            data.get("source_url", f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={set_id}")
        )

        return ParsedLabel(
            set_id=set_id,
            spl_id=spl_id,
            generic_name=generic_name,
            brand_names=brand_names,
            manufacturer=manufacturer,
            labeler=labeler,
            active_ingredients=active_ingredients,
            drug_classes=drug_classes,
            dosage_forms=dosage_forms,
            routes=routes,
            sections=sections,
            source_url=source_url,
            source_system="dailymed",
        )

    def parse_openfda_label(self, raw: dict[str, Any]) -> ParsedLabel:
        """Parse a raw openFDA label result dict (a single entry from results[])."""
        openfda = raw.get("openfda", {})

        set_id = _first_str(openfda.get("spl_set_id", []))
        spl_id = _first_str(openfda.get("spl_id", []))
        generic_name = _first_str(openfda.get("generic_name", []))

        brand_names: list[str] = openfda.get("brand_name", [])
        if isinstance(brand_names, str):
            brand_names = [brand_names]
        brand_names = [str(b) for b in brand_names if b]

        manufacturer = _first_str(openfda.get("manufacturer_name", []))
        labeler = _first_str(openfda.get("labeler_name", []))

        active_ingredients_raw = openfda.get("substance_name", raw.get("active_ingredient", []))
        if isinstance(active_ingredients_raw, str):
            active_ingredients = [active_ingredients_raw] if active_ingredients_raw else []
        else:
            active_ingredients = [str(a) for a in active_ingredients_raw if a]

        drug_classes: list[str] = openfda.get("pharm_class_epc", []) or openfda.get("pharm_class_moa", [])
        if isinstance(drug_classes, str):
            drug_classes = [drug_classes]
        drug_classes = [str(c) for c in drug_classes if c]

        dosage_forms: list[str] = _extract_list(openfda, "dosage_form")
        routes: list[str] = _extract_list(openfda, "route")

        # Parse sections from known openFDA field names
        openfda_section_fields: dict[str, str] = {
            "boxed_warning": "boxed_warning",
            "indications_and_usage": "indications_and_usage",
            "dosage_and_administration": "dosage_and_administration",
            "contraindications": "contraindications",
            "warnings_and_cautions": "warnings_and_precautions",
            "warnings": "warnings_and_precautions",
            "adverse_reactions": "adverse_reactions",
            "drug_interactions": "drug_interactions",
            "use_in_specific_populations": "use_in_specific_populations",
            "clinical_pharmacology": "clinical_pharmacology",
            "patient_counseling_information": "patient_counseling_information",
            "how_supplied": "how_supplied",
            "storage_and_handling": "storage_and_handling",
            "spl_unclassified_section": "patient_counseling_information",
        }

        sections: dict[str, str] = {}
        for raw_key, canonical in openfda_section_fields.items():
            value = raw.get(raw_key)
            if isinstance(value, list) and value:
                text = " ".join(str(v) for v in value if v)
                if text.strip():
                    sections[canonical] = text
            elif isinstance(value, str) and value.strip():
                sections[canonical] = value

        source_url = f"https://api.fda.gov/drug/label.json?search=openfda.spl_set_id:{set_id}"

        return ParsedLabel(
            set_id=set_id,
            spl_id=spl_id,
            generic_name=generic_name,
            brand_names=brand_names,
            manufacturer=manufacturer,
            labeler=labeler,
            active_ingredients=active_ingredients,
            drug_classes=drug_classes,
            dosage_forms=dosage_forms,
            routes=routes,
            sections=sections,
            source_url=source_url,
            source_system="openfda",
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _first_str(lst: list[Any], default: str = "") -> str:
    if lst and isinstance(lst, list):
        return str(lst[0]) if lst[0] else default
    if isinstance(lst, str):
        return lst
    return default


def _extract_list(data: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str) and value:
            return [value]
    return []
