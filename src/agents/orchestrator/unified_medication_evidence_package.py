from __future__ import annotations

from typing import Any


def build_unified_medication_evidence_package(
    medication_plan: dict,
    fhir_medication_result: dict,
    dailymed_result: dict,
    patient_context_package: dict | None = None,
) -> dict:
    patient_context_package = patient_context_package or {}
    medication_question_type = medication_plan.get("question_type", "unknown")
    explicit_drugs = []
    for item in medication_plan.get("explicit_drugs_mentioned", []) or []:
        if isinstance(item, dict):
            item_name = item.get("normalized_name") or item.get("raw_mention")
            explicit_drugs.append(
                {
                    "name": item_name,
                    "source": "user_message",
                    "dailymed_label_status": "available" if any(
                        str(ev.get("requested_target") or ev.get("drug_name") or "").lower().find(str(item_name or "").lower()) >= 0
                        for ev in dailymed_result.get("evidence", [])
                    ) else "missing",
                }
            )

    patient_active_medications = []
    for med in fhir_medication_result.get("medications", []) or []:
        if isinstance(med, dict):
            med_name = med.get("normalized_name") or med.get("display_name")
            patient_active_medications.append(
                {
                    "display_name": med.get("display_name"),
                    "normalized_name": med.get("normalized_name"),
                    "status": med.get("status"),
                    "dailymed_label_status": "available"
                    if any(
                        str(ev.get("requested_target") or ev.get("drug_name") or "").lower().find(str(med_name or "").lower()) >= 0
                        for ev in dailymed_result.get("evidence", [])
                    )
                    else "missing",
                }
            )

    safety_findings = []
    if medication_plan.get("comparison_needed"):
        safety_findings.append("Medication comparison required.")

    dailymed_summary = {
        "status": dailymed_result.get("status", "not_requested"),
        "requested_targets": [
            item.get("requested_target") or item.get("drug_name")
            for item in dailymed_result.get("evidence", [])
            if isinstance(item, dict)
        ],
        "labels_retrieved": sum(1 for item in dailymed_result.get("evidence", []) if item.get("matched_set_id")),
        "missing_labels": dailymed_result.get("missing_labels", []),
    }

    return {
        "medication_question_type": medication_question_type,
        "explicit_drugs": explicit_drugs,
        "patient_active_medications": patient_active_medications,
        "dailymed_evidence": dailymed_result.get("evidence", []),
        "dailymed_summary": dailymed_summary,
        "missing_medication_evidence": dailymed_result.get("missing_labels", []) + fhir_medication_result.get("missing_details", []),
        "safety_relevant_medication_findings": safety_findings,
        "medication_retrieval_plan": medication_plan,
        "patient_context_package": patient_context_package,
        "source_trace": {
            "fhir": fhir_medication_result.get("source_trace", []),
            "dailymed": dailymed_result.get("source_trace", []),
        },
        "warnings": fhir_medication_result.get("warnings", []) + dailymed_result.get("warnings", []),
        "comparison_needed": medication_plan.get("comparison_needed", False),
        "comparison_type": medication_plan.get("comparison_type", "none"),
    }
