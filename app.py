"""Cloud Run HTTP wrapper for the Empathica ADK orchestrator."""

from __future__ import annotations

import logging
import os
import json
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from agents.orchestrator.chat_orchestrator import ChatInput, run_chat
from onboarding.ingestion import onboard_user_with_files

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
    user_id: str = Field(..., min_length=1, description="Deterministic authenticated user identifier")
    message: str = Field(..., min_length=1, description="User prompt")
    patient_context: Optional[str] = Field(default=None)
    evidence: Optional[str] = Field(default=None)
    drug_set_ids: Optional[list[str]] = Field(default=None, description="Optional DailyMed SPL Set IDs")
    drug_names: Optional[list[str]] = Field(default=None, description="Optional medication names for DailyMed lookup")
    literacy_level: Optional[AllowedLevel] = Field(default=None)
    empathy_level: Optional[AllowedLevel] = Field(default=None)


class ChatResponse(BaseModel):
    answer: str
    literacy_level: AllowedLevel
    empathy_level: AllowedLevel
    debug: dict


class OnboardingResponse(BaseModel):
    user_id: str
    tenant: str
    fhir_patient_id: str
    docs_prefix: str
    docs_object_path: str
    status: str
    fhir_import_status: str


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "empathica-chatbot"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    payload = ChatInput(
        user_id=req.user_id,
        message=req.message,
        patient_context=req.patient_context,
        evidence=req.evidence,
        drug_set_ids=req.drug_set_ids,
        drug_names=req.drug_names,
        literacy_level=req.literacy_level,
        empathy_level=req.empathy_level,
    )

    try:
        out = run_chat(payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat execution failed: {type(exc).__name__}") from exc

    return ChatResponse(
        answer=out.answer,
        literacy_level=out.literacy_level,
        empathy_level=out.empathy_level,
        debug=out.debug,
    )


@app.post("/onboarding/upload", response_model=OnboardingResponse)
async def onboarding_upload(
    user_id: str = Form(...),
    tenant: str = Form("default"),
    status: str = Form("active"),
    structured_fhir_file: UploadFile = File(...),
    unstructured_file: UploadFile = File(...),
) -> OnboardingResponse:
    try:
        fhir_raw = await structured_fhir_file.read()
        fhir_json = json.loads(fhir_raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid structured_fhir_file JSON: {type(exc).__name__}") from exc

    unstructured_bytes = await unstructured_file.read()
    if not unstructured_bytes:
        raise HTTPException(status_code=400, detail="unstructured_file is empty.")

    try:
        result = onboard_user_with_files(
            user_id=user_id,
            tenant=tenant,
            status=status,
            structured_fhir_json=fhir_json,
            unstructured_filename=unstructured_file.filename or "unstructured.txt",
            unstructured_bytes=unstructured_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Onboarding failed: {type(exc).__name__}") from exc

    return OnboardingResponse(
        user_id=result.identity.user_id,
        tenant=result.identity.tenant,
        fhir_patient_id=result.fhir_patient_id,
        docs_prefix=result.docs_prefix,
        docs_object_path=result.docs_object_path,
        status=result.identity.status,
        fhir_import_status=result.fhir_import_status,
    )
