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

from agent import root_agent
from agents.literacy_assessor.scorer import score_message
from prompts_loader import load_prompt
from tools.allergy_check import build_allergy_context
from tools.fhir_patient_context import build_fhir_patient_context
from tools.drug_lookup import build_dailymed_context
from tools.literature_retrieval import build_evidence_context
from tools.patient_document_retrieval import build_patient_document_context
from tools.patient_document_selector import select_patient_document_needs
from tools.patient_context_selector import select_patient_context_needs

logger = logging.getLogger(__name__)

AllowedLevel = Literal["low", "medium", "high"]
APP_NAME = "empathica-chatbot"

_session_service = InMemorySessionService()
_runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=_session_service)


@dataclass
class ChatInput:
    message: str
    patient_context: Optional[str] = None
    evidence: Optional[str] = None
    drug_set_ids: Optional[list[str]] = None
    drug_names: Optional[list[str]] = None
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


def _infer_empathy_level(message: str, patient_context: str, evidence: str) -> AllowedLevel:
    t = f"{message} {patient_context} {evidence}".lower()
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

_KNOWN_DRUG_NAME_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ibuprofen", ("ibuprofen", "advil", "motrin")),
    ("acetaminophen", ("acetaminophen", "paracetamol", "tylenol")),
    ("ondansetron", ("ondansetron", "zofran")),
    ("dexamethasone", ("dexamethasone",)),
    ("filgrastim", ("filgrastim", "neupogen")),
    ("doxorubicin", ("doxorubicin", "adriamycin")),
    ("cyclophosphamide", ("cyclophosphamide", "cytoxan")),
    ("paclitaxel", ("paclitaxel", "taxol")),
    ("melatonin", ("melatonin",)),
)

_OVERCLAIM_PATTERNS = (
    r"\bbased on your (fhir|ehr|records?|labs?|chart)\b",
    r"\bi reviewed your (fhir|ehr|records?|labs?|documents?)\b",
    r"\byour (fhir|ehr) (shows|indicates)\b",
)

_SAFETY_DISCLAIMER = load_prompt("chat_medication_safety_disclaimer_v1.txt").strip()
_REFUSAL_RESPONSE = load_prompt("chat_refusal_self_harm_v1.txt").strip()
_EMPATHY_STYLE_LOW = load_prompt("chat_empathy_style_low_v1.txt").strip()
_EMPATHY_STYLE_MEDIUM = load_prompt("chat_empathy_style_medium_v1.txt").strip()
_EMPATHY_STYLE_HIGH = load_prompt("chat_empathy_style_high_v1.txt").strip()
_STRUCTURED_INPUT_TEMPLATE = load_prompt("chat_orchestrator_structured_input_template_v1.txt")


def _is_refusal_needed(message: str) -> bool:
    text = (message or "").lower()
    return any(k in text for k in _REFUSAL_KEYWORDS)


def _build_refusal_response() -> str:
    return _REFUSAL_RESPONSE


def _is_medication_question(message: str) -> bool:
    text = (message or "").lower()
    return any(k in text for k in _MEDICATION_QUESTION_KEYWORDS)


def _has_supporting_context(payload: ChatInput) -> bool:
    return bool(
        (payload.patient_context or "").strip()
        or (payload.evidence or "").strip()
        or payload.drug_set_ids
        or payload.drug_names
    )


def _has_overclaim(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(p, lower) for p in _OVERCLAIM_PATTERNS)


def _ensure_safety_disclaimer(answer: str) -> str:
    if _SAFETY_DISCLAIMER.lower() in (answer or "").lower():
        return answer
    return f"{answer.rstrip()}\n\n{_SAFETY_DISCLAIMER}".strip()


def _apply_output_guardrails(payload: ChatInput, answer: str) -> str:
    guarded = (answer or "").strip()
    if not guarded:
        return guarded

    if _is_refusal_needed(payload.message):
        return _build_refusal_response()

    # If there is no supporting context, prevent unsupported claims about reviewed records.
    if not _has_supporting_context(payload) and _has_overclaim(guarded):
        guarded = (
            "I do not have verified patient-specific records in this request, so I cannot confirm those details. "
            f"{guarded}"
        )

    if _is_medication_question(payload.message):
        guarded = _ensure_safety_disclaimer(guarded)

    return guarded


def _extract_drug_names_from_message(message: str) -> list[str]:
    text = (message or "").lower()
    found: list[str] = []
    for canonical, aliases in _KNOWN_DRUG_NAME_PATTERNS:
        if any(alias in text for alias in aliases):
            found.append(canonical)
    return found


def _shorten(text: str, limit: int = 520) -> str:
    t = " ".join((text or "").split()).strip()
    if len(t) <= limit:
        return t
    return t[: limit - 3].rstrip() + "..."


def _build_dailymed_debug_summary(message: str, retrieved_labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    message_l = (message or "").lower()
    section_order = [
        "contraindications",
        "warnings_precautions",
        "drug_interactions",
        "boxed_warning",
    ]
    cue_map = {
        "contraindications": ("contraindication", "avoid", "not take"),
        "warnings_precautions": ("warning", "risk", "safe", "danger", "pregnan", "kidney", "heart", "bleed"),
        "drug_interactions": ("interaction", "with my", "combine", "together"),
        "boxed_warning": ("boxed", "black box", "severe"),
    }

    summaries: list[dict[str, Any]] = []
    for label in retrieved_labels:
        sections = label.get("sections", {}) or {}
        selected_sections = []
        for sec in section_order:
            txt = sections.get(sec)
            if txt:
                selected_sections.append(sec)

        # Re-rank to move query-relevant sections first.
        selected_sections.sort(
            key=lambda sec: any(cue in message_l for cue in cue_map.get(sec, ())),
            reverse=True,
        )
        selected_sections = selected_sections[:3]

        summaries.append(
            {
                "setid": label.get("setid"),
                "title": label.get("title"),
                "source_url": label.get("source_url", ""),
                "multiple_matches": bool(label.get("multiple_matches", False)),
                "sections": {
                    sec: _shorten(str(sections.get(sec, "")))
                    for sec in selected_sections
                },
            }
        )
    return summaries


def _build_llm_dailymed_context(
    message: str,
    full_dailymed_ctx: str,
    retrieved_labels: list[dict[str, Any]],
) -> str:
    if not retrieved_labels:
        return full_dailymed_ctx

    message_l = (message or "").lower()

    always_include = {"contraindications", "boxed_warning", "warnings_precautions"}
    optional_by_intent = {
        "drug_interactions": ("interaction", "with my", "combine", "together", "mix"),
        "adverse_reactions": ("side effect", "adverse", "reaction", "symptom"),
        "dosage_administration": ("dose", "dosage", "how much", "how often", "take"),
        "use_specific_populations": ("pregnan", "breastfeeding", "elderly", "child", "kidney", "liver"),
        "indications_usage": ("what is", "what for", "used for", "indication"),
        "patient_counseling": ("what should i watch", "counsel", "advice"),
    }

    selected_optional = {
        sec
        for sec, cues in optional_by_intent.items()
        if any(cue in message_l for cue in cues)
    }
    target_sections = always_include.union(selected_optional)

    lines: list[str] = []
    included_any = False
    for label in retrieved_labels:
        setid = label.get("setid", "")
        title = label.get("title", "Unknown title")
        sections = label.get("sections", {}) or {}

        picked = [sec for sec in target_sections if sections.get(sec)]
        # Cautious default: if we only matched a small set, still add interactions and adverse reactions when available.
        if len(picked) < 3:
            for sec in ("drug_interactions", "adverse_reactions"):
                if sections.get(sec) and sec not in picked:
                    picked.append(sec)

        if not picked:
            continue

        included_any = True
        lines.append(f"Drug label: {title}")
        lines.append(f"Set ID: {setid}")
        pretty = {
            "boxed_warning": "Boxed Warning",
            "contraindications": "Contraindications",
            "warnings_precautions": "Warnings and Precautions",
            "drug_interactions": "Drug Interactions",
            "adverse_reactions": "Adverse Reactions",
            "indications_usage": "Indications and Usage",
            "dosage_administration": "Dosage and Administration",
            "use_specific_populations": "Use in Specific Populations",
            "patient_counseling": "Patient Counseling Information",
        }
        for sec in (
            "boxed_warning",
            "contraindications",
            "warnings_precautions",
            "drug_interactions",
            "adverse_reactions",
            "indications_usage",
            "dosage_administration",
            "use_specific_populations",
            "patient_counseling",
        ):
            if sec in picked and sections.get(sec):
                lines.append(f"- {pretty[sec]}: {sections[sec]}")
        lines.append("")

    if included_any:
        return "\n".join(lines).strip()
    return full_dailymed_ctx


def _build_structured_input(payload: ChatInput) -> tuple[str, dict]:
    selection = select_patient_context_needs(payload.message)
    fhir_ctx = build_fhir_patient_context(selection)
    document_selection = select_patient_document_needs(
        payload.message,
        selection.get("intent", "general_or_unclear"),
    )
    patient_document_ctx = build_patient_document_context(document_selection)
    user_supplied_ctx = (payload.patient_context or "").strip()
    evidence_ctx = build_evidence_context(payload.evidence)
    inferred_drug_names = []
    effective_drug_names = payload.drug_names
    if not payload.drug_set_ids and not payload.drug_names:
        inferred_drug_names = _extract_drug_names_from_message(payload.message)
        effective_drug_names = inferred_drug_names or None

    dailymed_ctx, meta = build_dailymed_context(
        drug_set_ids=payload.drug_set_ids,
        drug_names=effective_drug_names,
    )
    llm_dailymed_ctx = _build_llm_dailymed_context(
        payload.message,
        dailymed_ctx,
        list(meta.get("retrieved_labels", [])),
    )
    allergy_ctx = build_allergy_context(payload.patient_context, dailymed_ctx)
    logger.info(
        "patient_context_selection intent=%s requested_resources=%s fhir_context_len=%d",
        selection.get("intent", "general_or_unclear"),
        selection.get("needed_fhir_resources", []),
        len(fhir_ctx),
    )
    logger.info(
        "patient_document_selection types=%s query_term_count=%d document_context_len=%d",
        document_selection.get("needed_document_types", []),
        len(document_selection.get("query_terms", []) or []),
        len(patient_document_ctx),
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
        payload.evidence or "",
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
        intent=selection.get("intent", "general_or_unclear"),
        needed_context_categories=selection.get("needed_context_categories", []),
        needed_fhir_resources=selection.get("needed_fhir_resources", []),
        selection_reason=selection.get("reason", ""),
        fhir_ctx=fhir_ctx,
        user_supplied_ctx=user_supplied_ctx or "[none provided]",
        patient_document_ctx=patient_document_ctx,
        evidence_ctx=evidence_ctx,
        allergy_ctx=allergy_ctx,
        literacy_instruction=literacy_instruction,
        empathy_instruction=empathy_instruction,
        resolved_empathy=resolved_empathy,
        empathy_style_instruction=_empathy_style_instruction(resolved_empathy),
    )
    debug = {
        "dailymed": {
            "provided_drug_set_ids": payload.drug_set_ids or [],
            "provided_drug_names": payload.drug_names or [],
            "inferred_drug_names_from_message": inferred_drug_names,
            "used_drug_names": effective_drug_names or [],
            "set_ids_resolved": meta.get("set_ids_resolved", 0),
            "labels_retrieved": meta.get("labels_retrieved", 0),
            "labels_failed": meta.get("labels_failed", 0),
            "retrieved_labels": meta.get("retrieved_labels", []),
            "retrieved_labels_summary": _build_dailymed_debug_summary(
                payload.message,
                list(meta.get("retrieved_labels", [])),
            ),
            "unresolved_identifiers": meta.get("unresolved_identifiers", []),
        },
        "context_sent_to_llm": {
            "intent": selection.get("intent", "general_or_unclear"),
            "needed_fhir_resources": selection.get("needed_fhir_resources", []),
            "fhir_context": fhir_ctx,
            "user_supplied_context": user_supplied_ctx or "[none provided]",
            "patient_document_context": patient_document_ctx,
            "evidence_context": "" if evidence_ctx == "No evidence/literature context provided." else evidence_ctx,
            "allergy_context": allergy_ctx,
            "dailymed_context": (
                "See debug.dailymed.retrieved_labels_summary for concise, query-relevant sections."
                if meta.get("labels_retrieved", 0) > 0
                else dailymed_ctx
            ),
        },
    }
    return structured_input, debug


def run_chat(payload: ChatInput) -> ChatOutput:
    user_id = "api-user"
    session_id = _ensure_session(user_id)
    structured_input, debug = _build_structured_input(payload)

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
        f"{payload.patient_context or ''}\n{payload.evidence or ''}",
    )
    fallback_empathy: AllowedLevel = payload.empathy_level or _infer_empathy_level(
        payload.message,
        payload.patient_context or "",
        payload.evidence or "",
    )

    parsed = _extract_json_block(final_text)
    if not parsed:
        answer = _apply_output_guardrails(
            payload,
            _clean_patient_facing_answer(final_text) or final_text.strip(),
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
    answer = _apply_output_guardrails(payload, answer)

    return ChatOutput(
        answer=answer,
        literacy_level=_normalize_level(parsed.get("literacy_level"), fallback_literacy),
        empathy_level=_normalize_level(parsed.get("empathy_level"), fallback_empathy),
        debug=debug,
    )
