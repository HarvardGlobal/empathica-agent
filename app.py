"""Cloud Run HTTP wrapper for the Empathica ADK orchestrator."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agents.orchestrator.chat_orchestrator import ChatInput, run_chat

AllowedLevel = Literal["low", "medium", "high"]

app = FastAPI(title="Empathica Agent API", version="1.0.0")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User prompt")
    patient_context: Optional[str] = Field(default=None)
    evidence: Optional[str] = Field(default=None)
    drug_set_ids: Optional[list[str]] = Field(default=None, description="Optional DailyMed SPL Set IDs")
    drug_names: Optional[list[str]] = Field(default=None, description="Optional drug names for conservative DailyMed resolution")
    rxcuis: Optional[list[str]] = Field(default=None, description="Optional RxCUI identifiers")
    ndcs: Optional[list[str]] = Field(default=None, description="Optional NDC identifiers")
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
        drug_names=req.drug_names,
        rxcuis=req.rxcuis,
        ndcs=req.ndcs,
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
