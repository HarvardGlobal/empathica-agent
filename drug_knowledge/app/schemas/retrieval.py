from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class RetrievalPassage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: str
    section_type: str
    chunk_text: str
    score: float
    source_url: Optional[str] = None


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    passages: list[RetrievalPassage]
    source_type: str


class RAGRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    query: str
    drug_id: str
    section_types: list[str] = []
    top_k: int = 5


class StructuredFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data: dict[str, Any]
    source_type: str
    source_url: Optional[str] = None
    drug_id: str
