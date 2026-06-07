from __future__ import annotations

import re

from .medication_retrieval_plan_schema import (
    ExplicitDrugMention,
    FhirMedicationTarget,
    MedicationLookupTarget,
    MedicationRetrievalPlan,
    PatientMedicationScope,
)
from .medication_resolver import normalize_free_text_medication
from .literacy_control import detect_safety_override

_KNOWN_DRUG_NAMES = (
    "ibuprofen", "acetaminophen", "paracetamol", "aspirin", "melatonin",
    "ondansetron", "zofran", "dexamethasone", "filgrastim", "neupogen",
    "doxorubicin", "adriamycin", "cyclophosphamide", "cytoxan", "paclitaxel", "taxol",
    "lisinopril", "palbociclib", "warfarin",
)


def _contains(message: str, needles: list[str]) -> bool:
    text = (message or "").lower()
    return any(n in text for n in needles)


def _extract_explicit_drugs(message: str, provided_names: list[str] | None = None) -> list[ExplicitDrugMention]:
    found: list[ExplicitDrugMention] = []
    for raw in provided_names or []:
        cleaned = normalize_free_text_medication(raw)
        if cleaned:
            found.append(ExplicitDrugMention(raw_mention=raw, normalized_name=cleaned, confidence="high", reason="Provided in request."))
    lowered = (message or "").lower()
    for drug in _KNOWN_DRUG_NAMES:
        if re.search(rf"\b{re.escape(drug)}\b", lowered):
            if not any(item.normalized_name == drug for item in found):
                found.append(ExplicitDrugMention(raw_mention=drug, normalized_name=drug, confidence="high", reason="Explicitly mentioned in the user message."))
    return found


def plan_medication_evidence(
    message: str,
    explicit_drug_names: list[str] | None = None,
    drug_set_ids: list[str] | None = None,
    drug_rxcuis: list[str] | None = None,
    drug_ndcs: list[str] | None = None,
) -> MedicationRetrievalPlan:
    text = (message or "").strip()
    lowered = text.lower()
    explicit = _extract_explicit_drugs(text, provided_names=explicit_drug_names)
    has_specific_drug = bool(explicit or drug_set_ids or drug_rxcuis or drug_ndcs)

    urgent = detect_safety_override(text)
    if urgent:
        return MedicationRetrievalPlan(
            intent="urgent_medication_symptom",
            question_type="urgent medication symptom",
            risk_level="urgent",
            requires_medication_evidence=False,
            requires_patient_medication_list=False,
            missing_information_questions=[],
            safety_flags=["urgent_symptoms"],
            planner_rationale="Urgent symptom detected; do not delay escalation for medication retrieval.",
        )

    safety_drug_context = _contains(
        lowered,
        [
            "can i take",
            "safe with my current treatment",
            "with my current meds",
            "with my medications",
            "drug interaction",
            "interact with",
            "is this drug safe",
            "is this medication safe",
            "is ibuprofen safe",
            "safe for me",
        ],
    )

    if _contains(lowered, ["what drugs am i taking", "what am i taking", "my medications", "my meds", "current treatment"]) and not safety_drug_context and not explicit:
        return MedicationRetrievalPlan(
            intent="current_medication_list",
            question_type="current medication list question",
            risk_level="moderate",
            requires_medication_evidence=True,
            requires_patient_medication_list=True,
            explicit_drugs_mentioned=explicit,
            patient_medication_scope=PatientMedicationScope(True, "active_only", "The user asks about current medications or treatment."),
            dailymed_lookup_targets=[],
            fhir_medication_targets=[FhirMedicationTarget("active_patient_medications", "required", "The user asks about current medications or treatment.")],
            comparison_needed=False,
            comparison_type="none",
            safety_flags=["patient_medication_list_requested"],
            planner_rationale="Current medication list question needs the active medication list, not necessarily DailyMed.",
        )

    if safety_drug_context or (has_specific_drug and _contains(lowered, ["safe", "safe for me", "current treatment", "current meds", "current medications", "my medications", "my meds"])):
        targets: list[MedicationLookupTarget] = []
        for item in explicit:
            targets.append(MedicationLookupTarget("explicit_user_drug", item.normalized_name, "name", item.normalized_name, "required", "Explicit user drug mentioned in a medication safety question."))
        if not targets and (drug_set_ids or drug_rxcuis or drug_ndcs):
            targets.append(MedicationLookupTarget("explicit_user_drug", (drug_set_ids or drug_rxcuis or drug_ndcs or [""])[0], "unknown", (drug_set_ids or drug_rxcuis or drug_ndcs or [""])[0], "required", "Explicit drug input was provided."))
        if not targets and explicit:
            for item in explicit:
                targets.append(MedicationLookupTarget("explicit_user_drug", item.normalized_name, "name", item.normalized_name, "required", "Explicit user drug mentioned in a medication safety question."))
        return MedicationRetrievalPlan(
            intent="medication_safety",
            question_type="explicit drug safety with current treatment",
            risk_level="high",
            requires_medication_evidence=True,
            requires_patient_medication_list=True,
            explicit_drugs_mentioned=explicit,
            patient_medication_scope=PatientMedicationScope(True, "active_only", "Medication safety questions require the current medication list."),
            dailymed_lookup_targets=targets,
            fhir_medication_targets=[FhirMedicationTarget("active_patient_medications", "required", "Medication safety questions require the active medication list.")],
            comparison_needed=True,
            comparison_type="asked_drug_vs_current_meds",
            safety_flags=["medication_safety_question", "drug_interaction_question"],
            planner_rationale="Medication safety questions require comparing the asked drug against the current medication list.",
        )

    if _contains(lowered, ["fatigue", "tired", "sleepy", "side effect", "cause fatigue", "making me tired"]):
        return MedicationRetrievalPlan(
            intent="current_meds_side_effect_scan",
            question_type="current medication side effect scan",
            risk_level="moderate",
            requires_medication_evidence=True,
            requires_patient_medication_list=True,
            explicit_drugs_mentioned=explicit,
            patient_medication_scope=PatientMedicationScope(True, "active_only", "The question asks whether current medications could explain symptoms."),
            dailymed_lookup_targets=[],
            fhir_medication_targets=[FhirMedicationTarget("active_patient_medications", "required", "Symptom scan requires the active medication list.")],
            comparison_needed=True,
            comparison_type="current_meds_side_effect_scan",
            safety_flags=["medication_side_effect_question"],
            planner_rationale="Side effect questions require scanning the active medication list and enriching relevant meds.",
        )

    if _contains(lowered, ["interact with each other", "medications interact", "drug interaction", "interactions between"]):
        return MedicationRetrievalPlan(
            intent="current_meds_interaction_scan",
            question_type="current medication interaction scan",
            risk_level="moderate",
            requires_medication_evidence=True,
            requires_patient_medication_list=True,
            explicit_drugs_mentioned=explicit,
            patient_medication_scope=PatientMedicationScope(True, "active_only", "Interaction questions require the active medication list."),
            dailymed_lookup_targets=[],
            fhir_medication_targets=[FhirMedicationTarget("active_patient_medications", "required", "Interaction questions require the active medication list.")],
            comparison_needed=True,
            comparison_type="current_meds_interaction_scan",
            safety_flags=["medication_interaction_question"],
            planner_rationale="Interaction questions require comparing active medications with one another.",
        )

    if has_specific_drug:
        targets = [
            MedicationLookupTarget("explicit_user_drug", item.normalized_name, "name", item.normalized_name, "optional", "Explicit drug mentioned in the user question.")
            for item in explicit
        ]
        return MedicationRetrievalPlan(
            intent="drug_label_question",
            question_type="drug label question",
            risk_level="moderate",
            requires_medication_evidence=True,
            requires_patient_medication_list=False,
            explicit_drugs_mentioned=explicit,
            patient_medication_scope=PatientMedicationScope(False, "none", "No patient medication list is required unless personalization is needed."),
            dailymed_lookup_targets=targets,
            fhir_medication_targets=[],
            comparison_needed=False,
            comparison_type="none",
            safety_flags=["drug_label_question"] if targets else [],
            planner_rationale="Specific drug question can use DailyMed even without patient meds.",
        )

    if _contains(lowered, ["is this safe", "is it safe", "this medication", "my medication", "current treatment"]):
        return MedicationRetrievalPlan(
            intent="unclear_medication_reference",
            question_type="unclear medication reference",
            risk_level="unknown",
            requires_medication_evidence=False,
            requires_patient_medication_list=False,
            explicit_drugs_mentioned=[],
            patient_medication_scope=PatientMedicationScope(False, "none", "The medication reference is unclear."),
            missing_information_questions=["Which medication or treatment are you asking about?"],
            comparison_needed=False,
            comparison_type="none",
            safety_flags=["unclear_medication_reference"],
            planner_rationale="The question references medication ambiguously and needs clarification.",
        )

    return MedicationRetrievalPlan(
        intent="non_medication_question",
        question_type="non medication question",
        risk_level="unknown",
        requires_medication_evidence=False,
        requires_patient_medication_list=False,
        patient_medication_scope=PatientMedicationScope(False, "none", "No medication evidence is required."),
        comparison_needed=False,
        comparison_type="none",
        planner_rationale="The question does not clearly require medication evidence.",
    )
