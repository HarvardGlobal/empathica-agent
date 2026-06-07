from __future__ import annotations

from dataclasses import dataclass, field

from .context_catalog import CONTEXT_CATALOG
from .retrieval_plan_schema import RetrievalPlan, PlanContextItem


@dataclass
class ValidatedRetrievalPlan:
    validated_plan: RetrievalPlan
    removed_items: list[str] = field(default_factory=list)
    added_safety_context: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return {
            "validated_plan": self.validated_plan.to_dict(),
            "removed_items": self.removed_items,
            "added_safety_context": self.added_safety_context,
            "warnings": self.warnings,
            "fallback_used": self.fallback_used,
        }


def _dedupe(items: list[PlanContextItem]) -> list[PlanContextItem]:
    seen: set[str] = set()
    out: list[PlanContextItem] = []
    for item in items:
        if item.domain in seen:
            continue
        seen.add(item.domain)
        out.append(item)
    return out


def validate_retrieval_plan(plan: RetrievalPlan) -> ValidatedRetrievalPlan:
    removed_items: list[str] = []
    warnings: list[str] = []
    added_safety_context: list[str] = []
    fallback_used = False

    required: list[PlanContextItem] = []
    optional: list[PlanContextItem] = []

    for item in plan.required_context:
        if item.domain in CONTEXT_CATALOG:
            required.append(item)
        else:
            removed_items.append(item.domain)
            warnings.append(f"Unknown required domain removed: {item.domain}")
            fallback_used = True

    for item in plan.optional_context:
        if item.domain in CONTEXT_CATALOG:
            optional.append(item)
        else:
            removed_items.append(item.domain)
            warnings.append(f"Unknown optional domain removed: {item.domain}")
            fallback_used = True

    if plan.intent == "medication_safety":
        required_domains = {item.domain for item in required}
        if "active_medications" not in required_domains:
            required.append(PlanContextItem("active_medications", "Safety repair: current medications are needed.", "required"))
            added_safety_context.append("active_medications")
        if "allergies" not in required_domains:
            required.append(PlanContextItem("allergies", "Safety repair: allergies are needed.", "required"))
            added_safety_context.append("allergies")
        if "active_conditions" not in required_domains:
            required.append(PlanContextItem("active_conditions", "Safety repair: conditions are relevant.", "required"))
            added_safety_context.append("active_conditions")

    if plan.intent == "lab_interpretation":
        if not any(item.domain == "kidney_function" for item in required + optional):
            required.append(PlanContextItem("kidney_function", "Safety repair: renal markers are needed for lab interpretation.", "required"))
            added_safety_context.append("kidney_function")

    validated = RetrievalPlan(
        intent=plan.intent,
        question_type=plan.question_type,
        risk_level=plan.risk_level,
        requires_patient_specific_context=plan.requires_patient_specific_context,
        required_context=_dedupe(required),
        optional_context=_dedupe(optional),
        do_not_fetch=plan.do_not_fetch,
        missing_information_questions=plan.missing_information_questions,
        safety_flags=plan.safety_flags,
        planner_rationale=plan.planner_rationale,
    )
    return ValidatedRetrievalPlan(
        validated_plan=validated,
        removed_items=removed_items,
        added_safety_context=added_safety_context,
        warnings=warnings,
        fallback_used=fallback_used,
    )
