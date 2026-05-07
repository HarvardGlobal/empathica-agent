"""Cloud Run HTTP wrapper for the Empathica ADK orchestrator."""

from __future__ import annotations

import json
import os
from typing import Optional
from typing import Literal
from uuid import uuid4
import xml.etree.ElementTree as ET

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import httpx

from agent import root_agent

APP_NAME = os.environ.get("APP_NAME", "empathica-chatbot")

app = FastAPI(title="Empathica Agent API", version="1.0.0")

_session_service = InMemorySessionService()
_runner = Runner(app_name=APP_NAME, agent=root_agent, session_service=_session_service)

# Per-instance in-memory cache for DailyMed label context by SPL Set ID.
_dailymed_cache: dict[str, str] = {}
_dailymed_timeout = 12.0


AllowedLevel = Literal["low", "medium", "high"]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User prompt")
    patient_context: Optional[str] = Field(
        default=None,
        description="Optional long-form patient context.",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Optional long-form evidence/literature context.",
    )
    drug_set_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional DailyMed SPL Set IDs.",
    )
    literacy_level: Optional[AllowedLevel] = Field(
        default=None,
        description='Optional override: "low", "medium", or "high".',
    )
    empathy_level: Optional[AllowedLevel] = Field(
        default=None,
        description='Optional override: "low", "medium", or "high".',
    )


class ChatResponse(BaseModel):
    answer: str
    literacy_level: AllowedLevel
    empathy_level: AllowedLevel


def _ensure_session(user_id: str, session_id: Optional[str]) -> str:
    """Get or create an ADK session and return session id."""
    if session_id:
        existing = _session_service.get_session_sync(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if existing:
            return session_id

    created = _session_service.create_session_sync(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id or str(uuid4()),
    )
    return created.id


def _normalize_level(level: Optional[str], fallback: AllowedLevel) -> AllowedLevel:
    if not level:
        return fallback
    level_l = level.strip().lower()
    if level_l == "moderate":
        return "medium"
    if level_l in {"low", "medium", "high"}:
        return level_l  # type: ignore[return-value]
    return fallback


def _extract_text(content: Optional[types.Content]) -> str:
    if not content or not content.parts:
        return ""
    chunks: list[str] = []
    for part in content.parts:
        if part.text:
            chunks.append(part.text)
    return "\n".join(chunks).strip()


def _extract_json_block(text: str) -> Optional[dict]:
    text = text.strip()
    if not text:
        return None

    # 1) direct JSON object
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 2) markdown fenced block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _build_structured_input(req: ChatRequest) -> str:
    literacy_instruction = (
        f"Use this exact literacy level override: {req.literacy_level}."
        if req.literacy_level is not None
        else "Infer literacy level from user message and context. If uncertain, default to medium."
    )
    empathy_instruction = (
        f"Use this exact empathy level override: {req.empathy_level}."
        if req.empathy_level is not None
        else "Infer empathy level from emotional tone and context. If uncertain, default to medium."
    )
    dailymed_context, labels_retrieved, labels_failed, ids_provided = _build_dailymed_context(
        req.drug_set_ids
    )
    ids_provided_str = "true" if ids_provided else "false"

    return (
        "You are processing a structured clinical communication request.\n\n"
        "1. USER MESSAGE\n"
        f"{req.message}\n\n"
        "2. PATIENT CONTEXT\n"
        f"{req.patient_context or '[none provided]'}\n\n"
        "3. EVIDENCE / LITERATURE CONTEXT\n"
        f"{req.evidence or '[none provided]'}\n\n"
        "4. DAILYMED LABEL STATUS\n"
        f"- drug_set_ids_provided: {ids_provided_str}\n"
        f"- labels_retrieved: {labels_retrieved}\n"
        f"- labels_failed: {labels_failed}\n\n"
        "5. DAILYMED LABEL CONTEXT\n"
        f"{dailymed_context}\n\n"
        "6. LITERACY LEVEL INSTRUCTION\n"
        f"{literacy_instruction}\n\n"
        "7. EMPATHY LEVEL INSTRUCTION\n"
        f"{empathy_instruction}\n\n"
        "8. MEDICATION SAFETY AND EVIDENCE INSTRUCTION\n"
        "- Use DailyMed label context when available and relevant.\n"
        "- Do not invent label content.\n"
        "- Do not claim label evidence was reviewed unless label context is actually present.\n"
        "- If label context is missing or insufficient for a medication-specific question, state that clearly.\n"
        "- Use patient_context and evidence when provided.\n"
        "- If the question involves medication safety, provide cautious guidance and recommend confirming with a healthcare professional.\n\n"
        "9. OUTPUT FORMAT INSTRUCTION\n"
        "Return ONLY valid JSON with exactly these fields:\n"
        "{\n"
        '  "answer": "...",\n'
        '  "literacy_level": "low | medium | high",\n'
        '  "empathy_level": "low | medium | high"\n'
        "}\n"
    )


def _clean_set_id(set_id: str) -> str:
    return set_id.strip().lower()


def _find_section_texts(root: ET.Element) -> dict[str, str]:
    # SPL XML uses HL7 namespace; this path pattern works namespace-agnostically.
    sections = root.findall(".//{*}section")

    targets = [
        ("boxed_warning", ["boxed warning"]),
        ("contraindications", ["contraindications", "contraindication"]),
        ("warnings_precautions", ["warnings and precautions", "warnings & precautions", "warnings", "precautions"]),
        ("drug_interactions", ["drug interactions", "interactions"]),
        ("adverse_reactions", ["adverse reactions", "adverse events", "side effects"]),
        ("indications_usage", ["indications and usage", "indications"]),
        ("dosage_administration", ["dosage and administration", "dosage", "administration"]),
        ("use_specific_populations", ["use in specific populations", "specific populations", "pregnancy", "lactation", "pediatric use", "geriatric use"]),
        ("patient_counseling", ["patient counseling information", "information for patients", "patient information", "counseling"]),
    ]

    extracted: dict[str, str] = {}
    for section in sections:
        title_el = section.find("./{*}title")
        title = ""
        if title_el is not None:
            title = " ".join("".join(title_el.itertext()).split()).strip().lower()
        if not title:
            continue

        text_el = section.find("./{*}text")
        if text_el is None:
            continue
        text = " ".join("".join(text_el.itertext()).split()).strip()
        if not text:
            continue

        for key, patterns in targets:
            if key in extracted:
                continue
            if any(pat in title for pat in patterns):
                extracted[key] = text
                break

    return extracted


def _fetch_dailymed_label_context(set_id: str) -> str:
    cleaned = _clean_set_id(set_id)
    if cleaned in _dailymed_cache:
        return _dailymed_cache[cleaned]

    urls = [
        f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{cleaned}.xml",
        f"https://dailymed.nlm.nih.gov/dailymed/downloads/{cleaned}.xml",
    ]
    xml_text = None
    error_note = None

    for url in urls:
        try:
            response = httpx.get(url, timeout=_dailymed_timeout)
            if response.status_code == 200 and response.text.strip():
                xml_text = response.text
                break
        except Exception as exc:
            error_note = f"{type(exc).__name__}: {exc}"

    if not xml_text:
        msg = (
            f"Set ID {cleaned}: label could not be retrieved from DailyMed."
            + (f" Last error: {error_note}" if error_note else "")
        )
        _dailymed_cache[cleaned] = msg
        return msg

    try:
        root = ET.fromstring(xml_text)
        sections = _find_section_texts(root)
        if not sections:
            msg = f"Set ID {cleaned}: label retrieved, but relevant clinical sections were not found."
            _dailymed_cache[cleaned] = msg
            return msg

        ordered_keys = [
            "boxed_warning",
            "contraindications",
            "warnings_precautions",
            "drug_interactions",
            "adverse_reactions",
            "indications_usage",
            "dosage_administration",
            "use_specific_populations",
            "patient_counseling",
        ]
        pretty_names = {
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
        lines = [f"Set ID {cleaned}: DailyMed label context"]
        for key in ordered_keys:
            value = sections.get(key)
            if value:
                lines.append(f"- {pretty_names[key]}: {value}")
        msg = "\n".join(lines)
        _dailymed_cache[cleaned] = msg
        return msg
    except Exception as exc:
        msg = f"Set ID {cleaned}: label XML could not be parsed. Error: {type(exc).__name__}: {exc}"
        _dailymed_cache[cleaned] = msg
        return msg


def _build_dailymed_context(
    drug_set_ids: Optional[list[str]],
) -> tuple[str, int, int, bool]:
    # Optional input: if absent/empty, never fetch labels.
    if not drug_set_ids:
        return "No DailyMed drug label context was provided.", 0, 0, False

    cleaned_ids = []
    for raw in drug_set_ids:
        if not raw:
            continue
        c = _clean_set_id(raw)
        if c:
            cleaned_ids.append(c)
    if not cleaned_ids:
        return "No DailyMed drug label context was provided.", 0, 0, False

    # Preserve order, de-duplicate.
    unique_ids = list(dict.fromkeys(cleaned_ids))
    contexts = []
    labels_retrieved = 0
    labels_failed = 0
    for set_id in unique_ids:
        ctx = _fetch_dailymed_label_context(set_id)
        contexts.append(ctx)
        if "could not be retrieved" in ctx.lower() or "could not be parsed" in ctx.lower():
            labels_failed += 1
        elif "label retrieved" in ctx.lower() or "dailymed label context" in ctx.lower():
            labels_retrieved += 1
        else:
            # Conservative fallback: treat unknown outcomes as failures.
            labels_failed += 1

    if labels_retrieved == 0:
        return (
            "No DailyMed drug label context was provided.\n"
            + "\n\n".join(contexts),
            labels_retrieved,
            labels_failed,
            True,
        )

    return "\n\n".join(contexts), labels_retrieved, labels_failed, True


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "agent": root_agent.name}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # Keep ADK runner/session flow, but internalize session/user identifiers.
    user_id = "api-user"
    session_id = _ensure_session(user_id, None)
    structured_input = _build_structured_input(req)

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=structured_input)],
    )

    final_text = ""
    for event in _runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=user_message,
    ):
        if event.is_final_response():
            text = _extract_text(event.content)
            if text:
                final_text = text

    if not final_text:
        raise HTTPException(status_code=502, detail="No response generated by agent")

    fallback_literacy: AllowedLevel = req.literacy_level or "medium"
    fallback_empathy: AllowedLevel = req.empathy_level or "medium"

    parsed = _extract_json_block(final_text)
    if not parsed:
        return ChatResponse(
            answer=final_text,
            literacy_level=fallback_literacy,
            empathy_level=fallback_empathy,
        )

    answer = str(parsed.get("answer", "")).strip() or final_text
    literacy_level = _normalize_level(parsed.get("literacy_level"), fallback_literacy)
    empathy_level = _normalize_level(parsed.get("empathy_level"), fallback_empathy)

    return ChatResponse(
        answer=answer,
        literacy_level=literacy_level,
        empathy_level=empathy_level,
    )
