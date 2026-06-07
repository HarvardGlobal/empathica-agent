from __future__ import annotations

from .retrieval_plan_schema import RetrievalPlan


def normalize_context_package(retrieval_plan: RetrievalPlan, retrieval_results: dict, validation_result: dict) -> dict:
    domains = retrieval_results.get("domains", {}) or {}
    available_context = {}
    missing_context = list(retrieval_results.get("missing_context", []) or [])
    safety_relevant_findings: list[str] = []

    for domain, details in domains.items():
        available_context[domain] = details
        summary = str(details.get("summary", "") or "")
        status = str(details.get("status", "") or "")
        if status in {"available", "partially_available"} and summary:
            if domain in {"active_medications", "allergies", "active_conditions", "kidney_function", "liver_function", "blood_counts", "vital_signs", "bleeding_risk_context", "gi_risk_context", "cardiovascular_risk_context", "pregnancy_or_reproductive_context"}:
                safety_relevant_findings.append(summary)
        if details.get("missing_details"):
            for item in details["missing_details"]:
                if item not in missing_context:
                    missing_context.append(item)

    summary_parts = []
    for domain, details in available_context.items():
        if details.get("status") in {"available", "partially_available"}:
            summary_parts.append(str(details.get("summary", "")))
    patient_context_summary = " ".join(part for part in summary_parts if part).strip()

    return {
        "patient_context_summary": patient_context_summary,
        "available_context": available_context,
        "missing_context": missing_context,
        "safety_relevant_findings": safety_relevant_findings,
        "retrieval_plan_used": retrieval_plan.to_dict(),
        "retrieval_warnings": validation_result.get("warnings", []) + retrieval_results.get("warnings", []),
        "source_trace": retrieval_results.get("source_trace", []),
    }
