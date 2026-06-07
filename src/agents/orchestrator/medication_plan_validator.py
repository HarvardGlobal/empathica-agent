from __future__ import annotations

from dataclasses import dataclass, field

from .medication_retrieval_plan_schema import MedicationRetrievalPlan, MedicationLookupTarget, FhirMedicationTarget


@dataclass
class ValidatedMedicationPlan:
    validated_medication_plan: MedicationRetrievalPlan
    removed_items: list[str] = field(default_factory=list)
    added_safety_targets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return {
            "validated_medication_plan": self.validated_medication_plan.to_dict(),
            "removed_items": self.removed_items,
            "added_safety_targets": self.added_safety_targets,
            "warnings": self.warnings,
            "fallback_used": self.fallback_used,
        }


def _dedupe_lookup_targets(targets: list[MedicationLookupTarget]) -> list[MedicationLookupTarget]:
    seen: set[tuple[str, str]] = set()
    out: list[MedicationLookupTarget] = []
    for target in targets:
        key = (target.target_type, target.name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def validate_medication_plan(plan: MedicationRetrievalPlan) -> ValidatedMedicationPlan:
    removed_items: list[str] = []
    warnings: list[str] = []
    added_safety_targets: list[str] = []
    fallback_used = False

    explicit = plan.explicit_drugs_mentioned or []
    lookup_targets = plan.dailymed_lookup_targets or []
    fhir_targets = plan.fhir_medication_targets or []

    # Remove unknown target domains by construction: keep only target types in the allowed set.
    filtered_lookup: list[MedicationLookupTarget] = []
    for target in lookup_targets:
        if target.target_type in {"explicit_user_drug", "patient_active_medication", "comparison_drug"}:
            filtered_lookup.append(target)
        else:
            removed_items.append(target.name)
            warnings.append(f"Unknown medication lookup target removed: {target.name}")
            fallback_used = True

    if plan.risk_level in {"high", "urgent"} and not plan.requires_medication_evidence and plan.question_type != "urgent medication symptom":
        warnings.append("High-risk medication question promoted to medication evidence required.")
        fallback_used = True

    question_text = plan.question_type.lower()
    if "current medication" in question_text or "current treatment" in question_text or "my medication" in question_text:
        if not any(t.domain == "active_patient_medications" for t in fhir_targets):
            fhir_targets.append(FhirMedicationTarget("active_patient_medications", "required", "Current medication questions require the active medication list."))
            added_safety_targets.append("active_patient_medications")

    if plan.question_type in {"specific drug safety question", "current medication interaction scan", "current medication side effect scan"}:
        if not explicit and not filtered_lookup:
            warnings.append("Medication safety question lacks an explicit drug target.")
            fallback_used = True

    if len(filtered_lookup) > 8:
        filtered_lookup = filtered_lookup[:8]
        warnings.append("Capped DailyMed lookup targets at 8.")

    if plan.question_type == "current medication side effect scan" and not filtered_lookup:
        # Keep the active med list as the source; downstream resolver will derive label targets.
        added_safety_targets.append("drug_labels_for_active_meds")

    if plan.question_type == "specific drug safety question" and explicit and not filtered_lookup:
        for item in explicit:
            filtered_lookup.append(
                MedicationLookupTarget(
                    "explicit_user_drug",
                    item.normalized_name,
                    "name",
                    item.normalized_name,
                    "required",
                    "Safety repair: explicit drug should be included in DailyMed lookup targets.",
                )
            )
            added_safety_targets.append(item.normalized_name)

    validated = MedicationRetrievalPlan(
        intent=plan.intent,
        question_type=plan.question_type,
        risk_level=plan.risk_level,
        requires_medication_evidence=plan.requires_medication_evidence,
        requires_patient_medication_list=plan.requires_patient_medication_list,
        explicit_drugs_mentioned=explicit,
        patient_medication_scope=plan.patient_medication_scope,
        dailymed_lookup_targets=_dedupe_lookup_targets(filtered_lookup),
        fhir_medication_targets=fhir_targets,
        comparison_needed=plan.comparison_needed,
        comparison_type=plan.comparison_type,
        missing_information_questions=plan.missing_information_questions,
        safety_flags=plan.safety_flags,
        planner_rationale=plan.planner_rationale,
    )
    return ValidatedMedicationPlan(validated, removed_items, added_safety_targets, warnings, fallback_used)
