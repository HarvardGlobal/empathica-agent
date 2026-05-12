"""Cloud Run HTTP wrapper for the Empathica ADK orchestrator."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agents.orchestrator.chat_orchestrator import ChatInput, run_chat

AllowedLevel = Literal["low", "medium", "high"]
logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(_: FastAPI):
    model_name = os.getenv("GOOGLE_GENAI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    vertex_location = os.getenv("GOOGLE_CLOUD_LOCATION", "unset")
    logger.info("runtime_config model=%s vertex_location=%s", model_name, vertex_location)
    yield


app = FastAPI(title="Empathica Agent API", version="1.0.0", lifespan=_lifespan)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User prompt")
    patient_context: Optional[str] = Field(default=None)
    evidence: Optional[str] = Field(default=None)
    drug_set_ids: Optional[list[str]] = Field(default=None, description="Optional DailyMed SPL Set IDs")
    literacy_level: Optional[AllowedLevel] = Field(default=None)
    empathy_level: Optional[AllowedLevel] = Field(default=None)


class ChatResponse(BaseModel):
    answer: str
    literacy_level: AllowedLevel
    empathy_level: AllowedLevel


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "empathica-chatbot"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    payload = ChatInput(
        message=req.message,
        patient_context=req.patient_context,
        evidence=req.evidence,
        drug_set_ids=req.drug_set_ids,
        literacy_level=req.literacy_level,
        empathy_level=req.empathy_level,
    )

    try:
        out = run_chat(payload)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat execution failed: {type(exc).__name__}") from exc

    return ChatResponse(
        answer=out.answer,
        literacy_level=out.literacy_level,
        empathy_level=out.empathy_level,
    )
