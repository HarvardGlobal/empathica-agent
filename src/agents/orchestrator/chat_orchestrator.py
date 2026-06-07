from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ...agent import root_agent
from .literacy.scorer import score_message
from ...prompts_loader import load_prompt
from ...tools.patient.fhir_patient_context import build_fhir_patient_context
from ...tools.patient.identity_map import resolve_patient_identity
from ...tools.documents.patient_document_rag import retrieve_patient_document_context
from ...tools.patient.patient_context_selector import select_patient_context_needs
from .dailymed_context_executor import execute_dailymed_plan
from .fhir_medication_executor import execute_fhir_medication_plan
from .medication_planner import plan_medication_evidence
from .medication_plan_validator import validate_medication_plan
from .unified_medication_evidence_package import build_unified_medication_evidence_package
from .context_normalizer import normalize_context_package
from .fhir_context_executor import execute_retrieval_plan
from .orchestrator_context_planner import plan_context
from .retrieval_plan_validator import validate_retrieval_plan

logger = logging.getLogger(__name__)

AllowedLevel = Literal["low", "medium", "high"]
APP_NAME = "empathica-chatbot"

_session_service = InMemorySessionService()
_runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=_session_service)


@dataclass
class ChatInput:
    user_id: str
    message: str
    patient_context: Optional[str] = None
    drug_set_ids: Optional[list[str]] = None
    drug_names: Optional[list[str]] = None
    drug_rxcuis: Optional[list[str]] = None
    drug_ndcs: Optional[list[str]] = None
    literacy_level: Optional[AllowedLevel] = None
    empathy_level: Optional[AllowedLevel] = None


@dataclass
class ChatOutput:
    answer: str
    literacy_level: AllowedLevel
    empathy_level: AllowedLevel
    debug: dict


def _ensure_session(user_id: str) -> str:
    created = _session_service.create_session_sync(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=str(uuid4()),
    )
    return created.id


def _resolve_document_patient_id(identity: object) -> str:
    document_patient_id = getattr(identity, "document_patient_id", None)
    if isinstance(document_patient_id, str) and document_patient_id.strip():
        return document_patient_id.strip()
    docs_prefix = getattr(identity, "docs_prefix", None)
    if isinstance(docs_prefix, str) and docs_prefix.strip():
        prefix = docs_prefix.strip().strip("/")
        if prefix.startswith("patients/"):
            parts = [part for part in prefix.split("/") if part]
            if len(parts) >= 2:
                return parts[1]
    fhir_patient_id = getattr(identity, "fhir_patient_id", "")
    return str(fhir_patient_id or "").strip()


def _normalize_level(level: Optional[str], fallback: AllowedLevel) -> AllowedLevel:
    if not level:
        return fallback
    v = level.strip().lower()
    if v == "moderate":
        return "medium"
    if v in {"low", "medium", "high"}:
        return v  # type: ignore[return-value]
    return fallback


def _infer_literacy_level(message: str, context: str) -> AllowedLevel:
    scored = score_message(f"{message}\n{context}")
    level = scored.level
    if level == "moderate":
        return "medium"
    if level in {"low", "high"}:
        return level  # type: ignore[return-value]
    return "medium"


def _infer_empathy_level(message: str, patient_context: str) -> AllowedLevel:
    t = f"{message} {patient_context}".lower()
    high_signals = ["scared", "afraid", "worried", "pain", "anxious", "panic", "help"]
    low_signals = ["mechanism", "pharmacokinetics", "pathway", "trial", "cohort"]
    if any(s in t for s in high_signals):
        return "high"
    if any(s in t for s in low_signals):
        return "low"
    return "medium"


def _empathy_style_instruction(level: AllowedLevel) -> str:
    if level == "low":
        return _EMPATHY_STYLE_LOW
    if level == "high":
        return _EMPATHY_STYLE_HIGH
    return _EMPATHY_STYLE_MEDIUM


def _extract_text_from_content(content: object) -> str:
    if not content or not getattr(content, "parts", None):
        return ""
    chunks = []
    for part in content.parts:
        text = getattr(part, "text", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _extract_text_candidates_from_event(event: object) -> list[str]:
    candidates: list[str] = []

    content = getattr(event, "content", None)
    content_text = _extract_text_from_content(content)
    if content_text:
        candidates.append(content_text)

    for attr in ("text", "response"):
        value = getattr(event, attr, None)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
        elif value is not None:
            nested_text = getattr(value, "text", None)
            if isinstance(nested_text, str) and nested_text.strip():
                candidates.append(nested_text.strip())
            nested_content = getattr(value, "content", None)
            nested_content_text = _extract_text_from_content(nested_content)
            if nested_content_text:
                candidates.append(nested_content_text)

    return candidates


def _extract_json_block(text: str) -> Optional[dict]:
    text = text.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    fenced = re.search(r"```(?:json)?\\s*([\\s\\S]*?)\\s*```", text, re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _clean_patient_facing_answer(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned

    marker = "DRAFT RESPONSE:"
    idx = cleaned.find(marker)
    if idx != -1:
        cleaned = cleaned[idx + len(marker) :].strip()

    headers = ("LITERACY LEVEL:", "EMPATHY LEVEL:", "DISCLAIMER TYPE:", "STYLE CONTRACT:")
    lines = cleaned.splitlines()
    while lines:
        line = lines[0].strip()
        if not line:
            lines.pop(0)
            continue
        if any(line.startswith(h) for h in headers):
            lines.pop(0)
            continue
        break
    return "\n".join(lines).strip()


_REFUSAL_KEYWORDS = (
    "overdose",
    "kill myself",
    "harm myself",
    "suicide",
    "poison",
    "lethal dose",
)

_MEDICATION_QUESTION_KEYWORDS = (
    "take",
    "dose",
    "dosage",
    "medication",
    "medicine",
    "drug",
    "ibuprofen",
    "warfarin",
    "interaction",
    "side effect",
)

_OVERCLAIM_PATTERNS = (
    r"\bbased on your (fhir|ehr|records?|labs?|chart)\b",
    r"\bi reviewed your (fhir|ehr|records?|labs?|documents?)\b",
    r"\byour (fhir|ehr) (shows|indicates)\b",
)

_SAFETY_DISCLAIMER = load_prompt("chat_medication_safety_disclaimer_v2.txt").strip()
_REFUSAL_RESPONSE = load_prompt("chat_refusal_self_harm_v2.txt").strip()
_EMPATHY_STYLE_LOW = load_prompt("chat_empathy_style_low_v2.txt").strip()
_EMPATHY_STYLE_MEDIUM = load_prompt("chat_empathy_style_medium_v2.txt").strip()
_EMPATHY_STYLE_HIGH = load_prompt("chat_empathy_style_high_v2.txt").strip()
_STRUCTURED_INPUT_TEMPLATE = load_prompt("chat_orchestrator_structured_input_template_v2.txt")

_NO_RECORDS_DISCLAIMER_PATTERNS = (
    r"\bi (do not|don't|cannot|can't) (have|access) (verified )?(patient-specific|personal|your) (medical )?(records?|ehr|fhir).*?[.!?]",
    r"\bmy purpose is to provide general medical information.*?[.!?]",
)


def _is_refusal_needed(message: str) -> bool:
    text = (message or "").lower()
    return any(k in text for k in _REFUSAL_KEYWORDS)


def _build_refusal_response() -> str:
    return _REFUSAL_RESPONSE


def _is_medication_question(message: str) -> bool:
    text = (message or "").lower()
    return any(k in text for k in _MEDICATION_QUESTION_KEYWORDS)


def _has_supporting_context(payload: ChatInput, debug: Optional[dict] = None) -> bool:
    payload_has_context = bool(
        (payload.patient_context or "").strip()
        or payload.drug_set_ids
        or payload.drug_names
    )
    if payload_has_context:
        return True

    context_sent = (debug or {}).get("context_sent_to_llm", {}) if isinstance(debug, dict) else {}
    fhir_ctx = str(context_sent.get("fhir_context", "") or "")
    docs_ctx = str(context_sent.get("patient_document_context", "") or "")
    dailymed_ctx = str(context_sent.get("dailymed_context", "") or "")
    medication_debug = (debug or {}).get("medication", {}) if isinstance(debug, dict) else {}
    document_debug = (debug or {}).get("document_rag", {}) if isinstance(debug, dict) else {}

    has_fhir_selected = "FHIR PATIENT CONTEXT USED:" in fhir_ctx
    has_fhir_data = bool(re.search(r"resources_retrieved_counts:\s*\{[^}]*[1-9]", fhir_ctx))
    has_docs = docs_ctx and not any(
        phrase in docs_ctx
        for phrase in (
            "No patient-specific unstructured document context was selected",
            "No indexed patient document chunks were found.",
            "No relevant uploaded document snippet was found.",
        )
    )
    dailymed_status = str((medication_debug.get("dailymed", {}) or {}).get("status", "")).lower()
    has_dailymed = dailymed_status in {"available", "partial", "partially_available"} and bool(
        (medication_debug.get("dailymed", {}) or {}).get("evidence")
    )
    has_document_rag = str(document_debug.get("status", "")).lower() in {"available", "partial", "partially_available"} and bool(
        document_debug.get("snippets")
    )
    return bool(has_fhir_selected and has_fhir_data) or has_docs or has_dailymed or has_document_rag


def _has_overclaim(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(p, lower) for p in _OVERCLAIM_PATTERNS)


def _ensure_safety_disclaimer(answer: str) -> str:
    if _SAFETY_DISCLAIMER.lower() in (answer or "").lower():
        return answer
    return f"{answer.rstrip()}\n\n{_SAFETY_DISCLAIMER}".strip()


def _apply_output_guardrails(payload: ChatInput, answer: str, debug: Optional[dict] = None) -> str:
    guarded = (answer or "").strip()
    if not guarded:
        return guarded

    if _is_refusal_needed(payload.message):
        return _build_refusal_response()

    # If there is no supporting context, prevent unsupported claims about reviewed records.
    has_context = _has_supporting_context(payload, debug)
    if not has_context and _has_overclaim(guarded):
        guarded = (
            "I do not have verified patient-specific records in this request, so I cannot confirm those details. "
            f"{guarded}"
        )
    if has_context:
        for pattern in _NO_RECORDS_DISCLAIMER_PATTERNS:
            guarded = re.sub(pattern, "", guarded, flags=re.IGNORECASE).strip()
        guarded = re.sub(r"\n{3,}", "\n\n", guarded).strip()

    if _is_medication_question(payload.message):
        guarded = _ensure_safety_disclaimer(guarded)

    return guarded


def _build_retrieval_package(
    payload: ChatInput,
    fhir_patient_id: str,
    document_patient_id: str,
    docs_prefix: str,
) -> tuple[dict, str, str, list[str]]:
    """
    Build a controlled retrieval plan, validate it, execute only approved fetches,
    and normalize the results into a compact patient context package.
    """
    try:
        plan = plan_context(payload.message)
        validation = validate_retrieval_plan(plan)
        retrieval_results = execute_retrieval_plan(
            validation.validated_plan,
            fhir_patient_id=fhir_patient_id,
            document_patient_id=document_patient_id,
            docs_prefix=docs_prefix,
            user_message=payload.message,
        )
        normalized_package = normalize_context_package(
            validation.validated_plan,
            retrieval_results,
            validation.to_dict(),
        )
        fhir_ctx = json.dumps(normalized_package.get("available_context", {}), indent=2, sort_keys=True)
        patient_document_ctx = ""
        doc_context = normalized_package.get("available_context", {}).get("unstructured_patient_notes", {})
        if isinstance(doc_context, dict):
            patient_document_ctx = str(doc_context.get("summary", "") or "")
        return (
            {
                "plan": validation.validated_plan.to_dict(),
                "validation": validation.to_dict(),
                "execution": retrieval_results,
                "normalized": normalized_package,
            },
            fhir_ctx or "No patient specific FHIR context was selected for this request.",
            patient_document_ctx or "No patient-specific unstructured document context was selected.",
            list((validation.warnings or []) + (retrieval_results.get("warnings", []) or [])),
        )
    except Exception as exc:
        logger.warning("retrieval_plan_fallback reason=%s", type(exc).__name__)
        selection = select_patient_context_needs(payload.message)
        fhir_ctx = build_fhir_patient_context(selection, patient_id=fhir_patient_id)
        document_package = retrieve_patient_document_context(
            patient_id=document_patient_id,
            query=payload.message,
            docs_prefix=docs_prefix,
        )
        patient_document_ctx = str(document_package.get("summary", "") or "")
        fallback_package = {
            "plan": {
                "intent": selection.get("intent", "general_or_unclear"),
                "question_type": "fallback_deterministic_selector",
                "risk_level": "unknown",
                "requires_patient_specific_context": bool(selection.get("needed_fhir_resources")),
                "required_context": selection.get("needed_context_categories", []),
                "optional_context": [],
                "do_not_fetch": [],
                "missing_information_questions": [],
                "safety_flags": [],
                "planner_rationale": selection.get("reason", ""),
            },
            "validation": {"fallback_used": True, "warnings": [f"retrieval planner fallback: {type(exc).__name__}"]},
            "execution": {"warnings": [], "missing_context": [], "source_trace": []},
            "normalized": {
                "patient_context_summary": "",
                "available_context": {
                    "unstructured_patient_notes": {
                        "status": document_package.get("status", "unavailable"),
                        "summary": patient_document_ctx,
                        "structured_items": document_package.get("snippets", []),
                        "missing_details": document_package.get("missing_document_context", []),
                        "confidence": "medium" if document_package.get("snippets") else "low",
                        "document_rag_package": document_package,
                    }
                },
                "missing_context": [],
                "safety_relevant_findings": [],
                "retrieval_plan_used": selection,
                "retrieval_warnings": [f"retrieval planner fallback: {type(exc).__name__}"],
                "source_trace": [],
            },
        }
        return fallback_package, fhir_ctx, patient_document_ctx, [f"retrieval planner fallback: {type(exc).__name__}"]


def _build_medication_package(payload: ChatInput, fhir_patient_id: str, patient_context_package: dict | None = None) -> tuple[dict, list[str]]:
    try:
        medication_plan = plan_medication_evidence(
            payload.message,
            explicit_drug_names=payload.drug_names,
            drug_set_ids=payload.drug_set_ids,
            drug_rxcuis=payload.drug_rxcuis,
            drug_ndcs=payload.drug_ndcs,
        )
        validation = validate_medication_plan(medication_plan)
        fhir_medication_result = execute_fhir_medication_plan(validation.validated_medication_plan, patient_id=fhir_patient_id)
        dailymed_result = execute_dailymed_plan(
            validation.validated_medication_plan,
            fhir_medication_result.get("medications", []),
        )
        package = build_unified_medication_evidence_package(
            validation.validated_medication_plan.to_dict(),
            fhir_medication_result,
            dailymed_result,
            patient_context_package=patient_context_package,
        )
        warnings = list(validation.warnings or []) + list(fhir_medication_result.get("warnings", []) or []) + list(dailymed_result.get("warnings", []) or [])
        logger.info(
            "medication_planning question_type=%s explicit_drugs=%s fhir_med_count=%d dailymed_targets=%d fallback_used=%s warnings=%s",
            validation.validated_medication_plan.question_type,
            [item.normalized_name for item in validation.validated_medication_plan.explicit_drugs_mentioned],
            len(fhir_medication_result.get("medications", []) or []),
            len(dailymed_result.get("targets", []) or []),
            validation.fallback_used,
            warnings,
        )
        return {
            "plan": validation.validated_medication_plan.to_dict(),
            "validation": validation.to_dict(),
            "fhir": fhir_medication_result,
            "dailymed": dailymed_result,
            "unified": package,
        }, warnings
    except Exception as exc:
        logger.warning("medication_plan_fallback reason=%s", type(exc).__name__)
        fallback_plan = {
            "intent": "fallback",
            "question_type": "fallback medication inference",
            "risk_level": "unknown",
            "requires_medication_evidence": False,
            "requires_patient_medication_list": False,
            "explicit_drugs_mentioned": [],
            "patient_medication_scope": {"needed": False, "scope": "none", "reason": ""},
            "dailymed_lookup_targets": [],
            "fhir_medication_targets": [],
            "comparison_needed": False,
            "comparison_type": "none",
            "missing_information_questions": [],
            "safety_flags": [],
            "planner_rationale": f"medication planner fallback: {type(exc).__name__}",
        }
        package = {
            "medication_question_type": "fallback",
            "explicit_drugs": [],
            "patient_active_medications": [],
            "dailymed_evidence": [],
            "missing_medication_evidence": [f"medication planner fallback: {type(exc).__name__}"],
            "safety_relevant_medication_findings": [],
            "medication_retrieval_plan": fallback_plan,
            "source_trace": {"fhir": [], "dailymed": []},
            "warnings": [f"medication planner fallback: {type(exc).__name__}"],
            "comparison_needed": False,
            "comparison_type": "none",
        }
        return {
            "plan": fallback_plan,
            "validation": {"fallback_used": True, "warnings": [f"medication planner fallback: {type(exc).__name__}"]},
            "fhir": {"status": "unavailable", "medications": [], "missing_details": [], "warnings": [], "source_trace": []},
            "dailymed": {"status": "not_requested", "targets": [], "evidence": [], "missing_labels": [], "warnings": [], "source_trace": []},
            "unified": package,
        }, [f"medication planner fallback: {type(exc).__name__}"]


def _build_structured_input(
    payload: ChatInput,
    fhir_patient_id: str,
    document_patient_id: str,
    docs_prefix: str,
) -> tuple[str, dict]:
    retrieval_package, fhir_ctx, patient_document_ctx, retrieval_warnings = _build_retrieval_package(
        payload,
        fhir_patient_id=fhir_patient_id,
        document_patient_id=document_patient_id,
        docs_prefix=docs_prefix,
    )
    medication_package, medication_warnings = _build_medication_package(
        payload,
        fhir_patient_id=fhir_patient_id,
        patient_context_package=retrieval_package.get("normalized", {}),
    )
    retrieval_plan = json.dumps(retrieval_package.get("plan", {}), indent=2, sort_keys=True)
    normalized_context_package = json.dumps(retrieval_package.get("normalized", {}), indent=2, sort_keys=True)
    document_rag_package = retrieval_package.get("normalized", {}).get("available_context", {}).get("unstructured_patient_notes", {}).get("document_rag_package", {})
    medication_plan = json.dumps(medication_package.get("plan", {}), indent=2, sort_keys=True)
    unified_medication_package = json.dumps(medication_package.get("unified", {}), indent=2, sort_keys=True)
    combined_context_package = json.dumps(
        {
            "patient_context_package": retrieval_package.get("normalized", {}),
            "document_rag_package": document_rag_package,
            "medication_evidence_package": medication_package.get("unified", {}),
        },
        indent=2,
        sort_keys=True,
    )
    user_supplied_ctx = (payload.patient_context or "").strip()
    medication_dailymed = medication_package.get("dailymed", {})
    retrieved_labels = list(medication_dailymed.get("evidence", []))
    llm_dailymed_ctx = json.dumps(medication_dailymed, indent=2, sort_keys=True)
    meta = {
        "drug_identifiers_provided": bool(payload.drug_set_ids or payload.drug_names or payload.drug_rxcuis or payload.drug_ndcs),
        "set_ids_resolved": sum(1 for item in retrieved_labels if item.get("matched_set_id")),
        "labels_retrieved": sum(1 for item in retrieved_labels if item.get("matched_set_id")),
        "labels_failed": sum(1 for item in retrieved_labels if not item.get("matched_set_id")),
        "unresolved_identifiers": medication_dailymed.get("missing_labels", []),
        "retrieved_labels": retrieved_labels,
    }

    compact_retrieved_labels = [
        {
            "drug_name": label.get("drug_name"),
            "lookup_method": label.get("lookup_method"),
            "matched_set_id": label.get("matched_set_id"),
            "match_confidence": label.get("match_confidence"),
            "label_sections_available": label.get("label_sections_available", []),
        }
        for label in retrieved_labels
    ]
    retrieval_plan_obj = retrieval_package.get("plan", {})
    required_domains = [
        item.get("domain")
        for item in retrieval_plan_obj.get("required_context", [])
        if isinstance(item, dict) and item.get("domain")
    ]
    optional_domains = [
        item.get("domain")
        for item in retrieval_plan_obj.get("optional_context", [])
        if isinstance(item, dict) and item.get("domain")
    ]
    logger.info(
        "patient_context_planning intent=%s required_domains=%s optional_domains=%s fhir_context_len=%d",
        retrieval_plan_obj.get("intent", "general_or_unclear"),
        required_domains,
        optional_domains,
        len(fhir_ctx),
    )
    logger.info(
        "patient_document_context length=%d retrieval_warnings=%s",
        len(patient_document_ctx),
        retrieval_warnings,
    )

    literacy_instruction = (
        f"Use this exact literacy level override: {payload.literacy_level}."
        if payload.literacy_level is not None
        else "Infer literacy level from user message and context. If uncertain, default to medium."
    )
    empathy_instruction = (
        f"Use this exact empathy level override: {payload.empathy_level}."
        if payload.empathy_level is not None
        else "Infer empathy level from emotional tone and context. If uncertain, default to medium."
    )
    resolved_empathy = payload.empathy_level or _infer_empathy_level(
        payload.message,
        payload.patient_context or "",
    )

    structured_input = _STRUCTURED_INPUT_TEMPLATE.format(
        message=payload.message,
        drug_identifiers_provided=str(meta.get("drug_identifiers_provided", False)).lower(),
        set_ids_resolved=meta.get("set_ids_resolved", 0),
        labels_retrieved=meta.get("labels_retrieved", 0),
        labels_failed=meta.get("labels_failed", 0),
        unresolved_identifiers=meta.get("unresolved_identifiers", []),
        retrieved_labels=meta.get("retrieved_labels", []),
        dailymed_ctx=llm_dailymed_ctx,
        fhir_ctx=fhir_ctx,
        user_supplied_ctx=user_supplied_ctx or "[none provided]",
        patient_document_ctx=patient_document_ctx,
        document_rag_package=json.dumps(document_rag_package, indent=2, sort_keys=True) if document_rag_package else "[none]",
        literacy_instruction=literacy_instruction,
        empathy_instruction=empathy_instruction,
        resolved_empathy=resolved_empathy,
        empathy_style_instruction=_empathy_style_instruction(resolved_empathy),
        retrieval_plan=retrieval_plan,
        normalized_context_package=normalized_context_package,
        retrieval_warnings=retrieval_warnings or ["none"],
        medication_plan=medication_plan,
        unified_medication_package=unified_medication_package,
        combined_context_package=combined_context_package,
        medication_warnings=medication_warnings or ["none"],
    )
    debug = {
        "dailymed": {
            "provided_drug_set_ids": payload.drug_set_ids or [],
            "provided_drug_names": payload.drug_names or [],
            "inferred_drug_names_from_message": [item.get("normalized_name") for item in medication_package.get("plan", {}).get("explicit_drugs_mentioned", [])],
            "used_drug_names": [item.get("drug_name") for item in retrieved_labels if item.get("drug_name")],
            "set_ids_resolved": meta.get("set_ids_resolved", 0),
            "labels_retrieved": meta.get("labels_retrieved", 0),
            "labels_failed": meta.get("labels_failed", 0),
            "retrieved_labels": compact_retrieved_labels,
            "retrieved_labels_summary": retrieved_labels,
            "unresolved_identifiers": meta.get("unresolved_identifiers", []),
        },
        "context_sent_to_llm": {
            "retrieval_plan": retrieval_plan_obj,
            "normalized_context_package": retrieval_package.get("normalized", {}),
            "document_rag_package": document_rag_package,
            "medication_plan": medication_package.get("plan", {}),
            "unified_medication_package": medication_package.get("unified", {}),
            "fhir_context": fhir_ctx,
            "user_supplied_context": user_supplied_ctx or "[none provided]",
            "patient_document_context": patient_document_ctx,
            "dailymed_context": llm_dailymed_ctx,
        },
        "medication": {
            "warnings": medication_warnings,
            "plan": medication_package.get("plan", {}),
            "validation": medication_package.get("validation", {}),
            "fhir": medication_package.get("fhir", {}),
            "dailymed": medication_package.get("dailymed", {}),
            "unified": medication_package.get("unified", {}),
        },
        "document_rag": document_rag_package,
    }
    return structured_input, debug


def run_chat(payload: ChatInput) -> ChatOutput:
    identity = resolve_patient_identity(payload.user_id)
    if identity is None:
        raise LookupError("No patient identity mapping found for this user_id.")
    if identity.status != "active":
        raise PermissionError("User identity mapping is not active.")

    user_id = payload.user_id
    session_id = _ensure_session(user_id)
    document_patient_id = _resolve_document_patient_id(identity)
    structured_input, debug = _build_structured_input(
        payload,
        fhir_patient_id=identity.fhir_patient_id,
        document_patient_id=document_patient_id,
        docs_prefix=identity.docs_prefix,
    )
    debug["identity"] = {
        "user_id": identity.user_id,
        "tenant": identity.tenant,
        "fhir_patient_id": identity.fhir_patient_id,
        "document_patient_id": document_patient_id,
        "docs_prefix": identity.docs_prefix,
        "status": identity.status,
    }

    user_message = types.Content(role="user", parts=[types.Part(text=structured_input)])

    text_candidates: list[str] = []
    for event in _runner.run(user_id=user_id, session_id=session_id, new_message=user_message):
        candidates = _extract_text_candidates_from_event(event)
        selected = candidates[-1].strip() if candidates else ""
        if selected:
            text_candidates.append(selected)
        logger.info(
            "adk_event class=%s text_found=%s text_len=%d preview=%r",
            event.__class__.__name__,
            bool(selected),
            len(selected),
            selected[:200],
        )

    final_text = text_candidates[-1].strip() if text_candidates else ""
    if not final_text:
        raise ValueError("No response generated by agent")

    fallback_literacy: AllowedLevel = payload.literacy_level or _infer_literacy_level(
        payload.message,
        payload.patient_context or "",
    )
    fallback_empathy: AllowedLevel = payload.empathy_level or _infer_empathy_level(
        payload.message,
        payload.patient_context or "",
    )

    parsed = _extract_json_block(final_text)
    if not parsed:
        answer = _apply_output_guardrails(
            payload,
            _clean_patient_facing_answer(final_text) or final_text.strip(),
            debug,
        )
        return ChatOutput(
            answer=answer,
            literacy_level=fallback_literacy,
            empathy_level=fallback_empathy,
            debug=debug,
        )

    answer = _clean_patient_facing_answer(str(parsed.get("answer", "")).strip())
    if not answer:
        answer = _clean_patient_facing_answer(final_text) or final_text.strip()
    answer = _apply_output_guardrails(payload, answer, debug)

    return ChatOutput(
        answer=answer,
        literacy_level=_normalize_level(parsed.get("literacy_level"), fallback_literacy),
        empathy_level=_normalize_level(parsed.get("empathy_level"), fallback_empathy),
        debug=debug,
    )
