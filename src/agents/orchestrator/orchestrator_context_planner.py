from __future__ import annotations

from .context_catalog import CONTEXT_CATALOG
from .retrieval_plan_schema import PlanContextItem, RetrievalPlan
from .literacy_control import detect_safety_override


def _contains(message: str, needles: list[str]) -> bool:
    text = (message or "").lower()
    return any(n in text for n in needles)


def _make_required(domain: str, reason: str, lookback_days: int | None = None) -> PlanContextItem:
    return PlanContextItem(domain=domain, reason=reason, priority="required", lookback_days=lookback_days)


def _make_optional(domain: str, reason: str, lookback_days: int | None = None) -> PlanContextItem:
    return PlanContextItem(domain=domain, reason=reason, priority="optional", lookback_days=lookback_days)


def plan_context(message: str) -> RetrievalPlan:
    text = (message or "").strip()
    lowered = text.lower()

    if detect_safety_override(text):
        return RetrievalPlan(
            intent="urgent_symptom_triage",
            question_type="urgent symptom triage",
            risk_level="urgent",
            requires_patient_specific_context=False,
            required_context=[],
            optional_context=[],
            do_not_fetch=[{"domain": "patient_record", "reason": "Urgent escalation should not be delayed by retrieval."}],
            missing_information_questions=[],
            safety_flags=["urgent_symptoms"],
            planner_rationale="Emergency signal detected; escalate without retrieval delay.",
        )

    if _contains(lowered, ["what is ibuprofen", "what is acetaminophen", "what is melatonin", "what is this medicine", "what does this drug do"]):
        return RetrievalPlan(
            intent="general_education",
            question_type="general education",
            risk_level="low",
            requires_patient_specific_context=False,
            planner_rationale="General education question; no patient-specific data required.",
        )

    if _contains(lowered, ["what does my egfr mean", "creatinine", "kidney function", "renal", "bun"]):
        return RetrievalPlan(
            intent="lab_interpretation",
            question_type="lab interpretation",
            risk_level="moderate",
            requires_patient_specific_context=True,
            required_context=[
                _make_required("kidney_function", "The question asks about renal markers."),
            ],
            optional_context=[
                _make_optional("active_medications", "Medications may affect renal interpretation."),
                _make_optional("active_conditions", "Kidney-related conditions can contextualize lab values."),
                _make_optional("demographics", "Age can influence interpretation."),
            ],
            safety_flags=["lab_interpretation"],
            planner_rationale="Renal markers are the primary needed context.",
        )

    if _contains(lowered, ["ibuprofen", "safe with", "drug interaction", "can i take", "with my current treatment", "painkiller", "nsaid"]):
        return RetrievalPlan(
            intent="medication_safety",
            question_type="medication safety",
            risk_level="high",
            requires_patient_specific_context=True,
            required_context=[
                _make_required("active_medications", "Medication safety depends on the current medication list."),
                _make_required("allergies", "Allergies are required for medication safety."),
                _make_required("active_conditions", "Comorbid conditions can change safety."),
            ],
            optional_context=[
                _make_optional("kidney_function", "Renal function affects NSAID and medication safety.", 180),
                _make_optional("liver_function", "Liver function can affect safety and metabolism.", 180),
                _make_optional("blood_counts", "Blood counts can affect bleeding/infection risk.", 180),
                _make_optional("bleeding_risk_context", "Bleeding history affects NSAID risk.", 365),
                _make_optional("gi_risk_context", "GI history affects NSAID risk.", 365),
                _make_optional("cardiovascular_risk_context", "Cardiovascular risk can matter for NSAIDs.", 365),
            ],
            safety_flags=["medication_safety_question"],
            planner_rationale="Medication safety questions require meds, allergies, and condition context.",
        )

    if _contains(lowered, ["chest pain", "shortness of breath", "trouble breathing", "can't breathe", "cannot breathe"]):
        return RetrievalPlan(
            intent="urgent_symptom_triage",
            question_type="urgent symptom triage",
            risk_level="urgent",
            requires_patient_specific_context=False,
            safety_flags=["urgent_symptoms"],
            planner_rationale="Urgent symptoms require immediate escalation rather than retrieval.",
        )

    return RetrievalPlan(
        intent="general_or_unclear",
        question_type="unclear question",
        risk_level="unknown",
        requires_patient_specific_context=False,
        planner_rationale="Intent is unclear; defaulting to a minimal safe retrieval posture.",
    )


def known_domains() -> tuple[str, ...]:
    return tuple(CONTEXT_CATALOG.keys())
