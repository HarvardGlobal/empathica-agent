from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent import root_agent
from agents.literacy_assessor.scorer import score_message
from tools.allergy_check import build_allergy_context
from tools.fhir_patient_context import build_fhir_patient_context
from tools.drug_lookup import build_dailymed_context
from tools.literature_retrieval import build_evidence_context
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
    literacy_level: Optional[AllowedLevel] = None
    empathy_level: Optional[AllowedLevel] = None


@dataclass
class ChatOutput:
    answer: str
    literacy_level: AllowedLevel
    empathy_level: AllowedLevel


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

    headers = ("LITERACY LEVEL:", "DISCLAIMER TYPE:", "STYLE CONTRACT:")
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


def _build_structured_input(payload: ChatInput) -> str:
    selection = select_patient_context_needs(payload.message)
    fhir_ctx = build_fhir_patient_context(selection)
    user_supplied_ctx = (payload.patient_context or "").strip()
    evidence_ctx = build_evidence_context(payload.evidence)
    dailymed_ctx, meta = build_dailymed_context(
        drug_set_ids=payload.drug_set_ids,
    )
    allergy_ctx = build_allergy_context(payload.patient_context, dailymed_ctx)
    logger.info(
        "patient_context_selection intent=%s requested_resources=%s fhir_context_len=%d",
        selection.get("intent", "general_or_unclear"),
        selection.get("needed_fhir_resources", []),
        len(fhir_ctx),
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

    return (
        "You are processing a structured clinical communication request.\\n\\n"
        "1. USER MESSAGE\\n"
        f"{payload.message}\\n\\n"
        "2. DAILYMED LABEL STATUS\\n"
        f"- drug_identifiers_provided: {str(meta.get('drug_identifiers_provided', False)).lower()}\\n"
        f"- set_ids_resolved: {meta.get('set_ids_resolved', 0)}\\n"
        f"- labels_retrieved: {meta.get('labels_retrieved', 0)}\\n"
        f"- labels_failed: {meta.get('labels_failed', 0)}\\n"
        f"- unresolved_identifiers: {meta.get('unresolved_identifiers', [])}\\n"
        f"- retrieved_labels: {meta.get('retrieved_labels', [])}\\n\\n"
        "3. DAILYMED LABEL CONTEXT\\n"
        f"{dailymed_ctx}\\n\\n"
        "4. PATIENT CONTEXT SELECTION\\n"
        f"Intent: {selection.get('intent', 'general_or_unclear')}\\n"
        f"Needed context categories: {selection.get('needed_context_categories', [])}\\n"
        f"Needed FHIR resources: {selection.get('needed_fhir_resources', [])}\\n"
        f"Reason: {selection.get('reason', '')}\\n\\n"
        "5. FHIR PATIENT CONTEXT\\n"
        f"{fhir_ctx}\\n\\n"
        "6. USER PROVIDED SUPPLEMENTARY PATIENT CONTEXT\\n"
        f"{user_supplied_ctx or '[none provided]'}\\n\\n"
        "7. EVIDENCE / LITERATURE CONTEXT\\n"
        f"{evidence_ctx}\\n\\n"
        "8. ALLERGY CONTEXT\\n"
        f"{allergy_ctx}\\n\\n"
        "9. LITERACY LEVEL INSTRUCTION\\n"
        f"{literacy_instruction}\\n\\n"
        "10. EMPATHY LEVEL INSTRUCTION\\n"
        f"{empathy_instruction}\\n\\n"
        "11. MEDICATION SAFETY AND EVIDENCE INSTRUCTION\\n"
        "- Use DailyMed label context when available and relevant.\\n"
        "- Use FHIR patient context when relevant and available.\\n"
        "- Use manually provided patient_context only as supplementary context.\\n"
        "- Use the selected patient context only if it is available.\\n"
        "- Do not invent missing patient facts.\\n"
        "- If important patient context is missing, state that the answer is limited by missing information.\\n"
        "- Do not claim that full FHIR/EHR data was reviewed.\\n"
        "- If patient context was user-provided supplementary text, do not describe it as verified FHIR data.\\n"
        "- Use patient_context and evidence when provided.\\n"
        "- Never invent drug label content, patient facts, allergies, or sources.\\n"
        "- If label context is missing or insufficient for a medication-specific question, say so clearly.\\n"
        "- If the question involves medication safety, provide cautious guidance and recommend confirming with the clinical team or pharmacist.\\n\\n"
        "12. OUTPUT FORMAT INSTRUCTION\\n"
        "Return ONLY valid JSON with exactly these fields:\\n"
        "{\\n"
        '  "answer": "...",\\n'
        '  "literacy_level": "low | medium | high",\\n'
        '  "empathy_level": "low | medium | high"\\n'
        "}\\n"
        "The answer value must contain only the final patient-facing answer.\\n"
        "It must not contain DRAFT RESPONSE, STYLE CONTRACT, DISCLAIMER TYPE, LITERACY LEVEL, internal planning, style metadata, or chain of thought.\\n"
    )


def run_chat(payload: ChatInput) -> ChatOutput:
    user_id = "api-user"
    session_id = _ensure_session(user_id)
    structured_input = _build_structured_input(payload)

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
        return ChatOutput(
            answer=_clean_patient_facing_answer(final_text) or final_text.strip(),
            literacy_level=fallback_literacy,
            empathy_level=fallback_empathy,
        )

    answer = _clean_patient_facing_answer(str(parsed.get("answer", "")).strip())
    if not answer:
        answer = _clean_patient_facing_answer(final_text) or final_text.strip()

    return ChatOutput(
        answer=answer,
        literacy_level=_normalize_level(parsed.get("literacy_level"), fallback_literacy),
        empathy_level=_normalize_level(parsed.get("empathy_level"), fallback_empathy),
    )
