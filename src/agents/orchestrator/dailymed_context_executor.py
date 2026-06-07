from __future__ import annotations

from typing import Any

from ...tools.medications.drug_lookup import build_dailymed_context
from .medication_retrieval_plan_schema import MedicationRetrievalPlan, MedicationLookupTarget
from .medication_resolver import resolve_medication_name


def _summarize_sections(label: dict[str, Any], question_type: str) -> dict[str, Any]:
    sections = label.get("sections", {}) or {}
    question = (question_type or "").lower()
    wanted = [
        "warnings_precautions",
        "contraindications",
        "drug_interactions",
        "adverse_reactions",
        "dosage_administration",
        "use_specific_populations",
    ]
    if "side effect" in question:
        wanted = ["adverse_reactions", "warnings_precautions", "contraindications"]
    elif "interaction" in question:
        wanted = ["drug_interactions", "contraindications", "warnings_precautions"]
    elif "pregnan" in question or "reproductive" in question:
        wanted = ["use_specific_populations", "warnings_precautions", "contraindications"]
    elif "dose" in question or "administration" in question:
        wanted = ["dosage_administration", "warnings_precautions", "contraindications"]
    return {
        "contraindications_summary": sections.get("contraindications", ""),
        "warnings_and_precautions_summary": sections.get("warnings_precautions", ""),
        "adverse_reactions_summary": sections.get("adverse_reactions", ""),
        "drug_interactions_summary": sections.get("drug_interactions", ""),
        "dosage_and_administration_summary": sections.get("dosage_administration", ""),
        "use_in_specific_populations_summary": sections.get("use_specific_populations", ""),
        "label_sections_available": list(sections.keys()),
        "_wanted_sections": wanted,
    }


_SUPPORTIVE_ITEM_TERMS = (
    "tea",
    "herbal",
    "herb",
    "peppermint",
    "ginger",
    "multivitamin",
    "vitamin",
    "supplement",
    "nutrition",
    "food",
    "probiotic",
    "omega-3",
    "fish oil",
    "turmeric",
    "garlic",
    "supportive",
)


def _is_supportive_item(name: str) -> bool:
    text = (name or "").lower()
    return any(term in text for term in _SUPPORTIVE_ITEM_TERMS)


def _should_auto_add_active_medications(plan: MedicationRetrievalPlan) -> bool:
    return plan.question_type in {"current medication side effect scan", "current medication interaction scan"}


def _lookup_from_target(target: MedicationLookupTarget) -> dict[str, Any]:
    resolution = resolve_medication_name(target.name)
    drug_names = resolution.lookup_candidates[:3] or ([target.name] if target.name else [])
    context, meta = build_dailymed_context(
        drug_names=drug_names if target.identifier_type == "name" or not target.identifier_value else None,
        rxcuis=[target.identifier_value] if target.identifier_type == "rxcui" and target.identifier_value else None,
        ndcs=[target.identifier_value] if target.identifier_type == "ndc" and target.identifier_value else None,
        drug_set_ids=[target.identifier_value] if target.identifier_type == "set_id" and target.identifier_value else None,
    )
    retrieved = meta.get("retrieved_labels", [])
    if not retrieved and drug_names and target.identifier_type == "unknown":
        context, meta = build_dailymed_context(drug_names=drug_names)
        retrieved = meta.get("retrieved_labels", [])
    if not retrieved:
        return {
            "requested_target": target.name,
            "drug_name": target.name,
            "matched_label_title": None,
            "match_note": f"No DailyMed label found for requested target {target.name}.",
            "lookup_method": target.identifier_type,
            "matched_set_id": None,
            "match_confidence": "low",
            "label_sections_available": [],
            "warnings": meta.get("unresolved_identifiers", []) or [f"No DailyMed match for {target.name}"],
            "contraindications_summary": "",
            "warnings_and_precautions_summary": "",
            "adverse_reactions_summary": "",
            "drug_interactions_summary": "",
            "dosage_and_administration_summary": "",
            "use_in_specific_populations_summary": "",
            "source_trace": meta,
        }
    label = retrieved[0]
    summary = _summarize_sections(label, target.reason)
    match_note = "Matched to an available product label. Product formulation may not match the exact patient product."
    if target.identifier_type in {"ndc", "set_id"}:
        match_note = "Matched to an identified product label."
    return {
        "requested_target": target.name,
        "drug_name": target.name,
        "matched_label_title": label.get("title") or target.name,
        "match_note": match_note,
        "lookup_method": target.identifier_type or "name",
        "matched_set_id": label.get("setid"),
        "match_confidence": "high" if label.get("setid") else "medium",
        "label_sections_available": summary["label_sections_available"],
        "warnings": meta.get("unresolved_identifiers", []),
        "contraindications_summary": summary["contraindications_summary"],
        "warnings_and_precautions_summary": summary["warnings_and_precautions_summary"],
        "adverse_reactions_summary": summary["adverse_reactions_summary"],
        "drug_interactions_summary": summary["drug_interactions_summary"],
        "dosage_and_administration_summary": summary["dosage_and_administration_summary"],
        "use_in_specific_populations_summary": summary["use_in_specific_populations_summary"],
        "source_trace": {
            "build_dailymed_context": meta,
        },
    }


def execute_dailymed_plan(plan: MedicationRetrievalPlan, fhir_medications: list[dict[str, Any]] | None = None) -> dict:
    targets: list[MedicationLookupTarget] = list(plan.dailymed_lookup_targets or [])

    if fhir_medications and _should_auto_add_active_medications(plan):
        max_targets = 5
        existing = {target.name.lower() for target in targets}
        for med in fhir_medications[:max_targets]:
            name = str(med.get("normalized_name") or med.get("display_name") or "").strip()
            if not name or name.lower() in existing or _is_supportive_item(name):
                continue
            targets.append(
                MedicationLookupTarget(
                    target_type="patient_active_medication",
                    name=name,
                    identifier_type="name",
                    identifier_value=name,
                    priority="optional",
                    reason="Relevant active patient medication selected for enrichment.",
                )
            )
            existing.add(name.lower())

    evidence = [_lookup_from_target(target) for target in targets]
    missing = [
        f"No DailyMed label was confidently matched for {item['requested_target']}."
        for item in evidence
        if not item.get("matched_set_id")
    ]
    return {
        "status": "available" if evidence else "not_requested",
        "targets": [target.__dict__ for target in targets],
        "evidence": evidence,
        "missing_labels": missing,
        "warnings": [],
        "source_trace": [item.get("source_trace", {}) for item in evidence],
    }
