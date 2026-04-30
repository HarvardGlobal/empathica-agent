from __future__ import annotations

from typing import Any, Optional, Union

from sqlalchemy.orm import Session

from app.schemas.retrieval import (
    RAGRequest,
    RetrievalPassage,
    RetrievalResponse,
    StructuredFactResponse,
)
from app.services.drug_facts import DrugFactsService
from app.services.interactions import InteractionService
from app.services.patient_meds import PatientMedService


# Valid question_type values and their routing destinations
STRUCTURED_ROUTES: set[str] = {
    "basic_profile",
    "purpose_high",
    "purpose_moderate",
    "purpose_low",
    "common_side_effects",
    "serious_side_effects",
    "contraindications",
    "warnings",
    "pregnancy",
    "breastfeeding",
    "renal",
    "hepatic",
    "interaction",
    "patient_medications",
}

VECTOR_ROUTES: set[str] = {
    "rag",
    "freeform",
    "section_search",
}


class RetrievalRouter:
    """
    Routes retrieval requests to the appropriate backend based on question_type.

    Structured routes  -> DrugFactsService / InteractionService / PatientMedService
    Vector routes      -> VectorIndex search
    """

    def __init__(
        self,
        db: Session,
        vector_index: Any,
        drug_facts: DrugFactsService,
        interactions: InteractionService,
        patient_meds: PatientMedService,
    ) -> None:
        self._db = db
        self._vector_index = vector_index
        self._drug_facts = drug_facts
        self._interactions = interactions
        self._patient_meds = patient_meds

    def route(
        self,
        question_type: str,
        drug_id: str,
        *,
        # Optional contextual params
        drug_b_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        literacy_level: str = "moderate",
        population_type: Optional[str] = None,
        query_embedding: Optional[list[float]] = None,
        section_types: Optional[list[str]] = None,
        top_k: int = 5,
    ) -> Union[StructuredFactResponse, RetrievalResponse]:
        """
        Route a retrieval request to the correct backend.

        Routing rules:
        - basic_profile        -> drug_facts.get_drug_basic_profile
        - purpose_*            -> drug_facts.get_drug_purpose (literacy from suffix)
        - common_side_effects  -> drug_facts.get_common_side_effects
        - serious_side_effects -> drug_facts.get_serious_side_effects
        - contraindications    -> drug_facts.get_contraindication_summary
        - warnings             -> drug_facts.get_warning_summary
        - pregnancy / breastfeeding / renal / hepatic -> get_special_population_summary
        - interaction          -> interactions.get_interaction (requires drug_b_id)
        - patient_medications  -> patient_meds.get_patient_medications (requires patient_id)
        - rag / freeform / section_search -> vector_index.search
        """
        qt = question_type.lower()

        # ----------------------------------------------------------------
        # Structured routes
        # ----------------------------------------------------------------
        if qt == "basic_profile":
            data = self._drug_facts.get_drug_basic_profile(drug_id)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt in ("purpose_high", "purpose_moderate", "purpose_low"):
            level = qt.split("_", 1)[1]  # "high", "moderate", or "low"
            data = self._drug_facts.get_drug_purpose(drug_id, level)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt == "common_side_effects":
            data = self._drug_facts.get_common_side_effects(drug_id)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt == "serious_side_effects":
            data = self._drug_facts.get_serious_side_effects(drug_id)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt == "contraindications":
            data = self._drug_facts.get_contraindication_summary(drug_id)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt == "warnings":
            data = self._drug_facts.get_warning_summary(drug_id)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt in ("pregnancy", "breastfeeding", "renal", "hepatic"):
            pop_type = population_type or qt
            data = self._drug_facts.get_special_population_summary(drug_id, pop_type)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt == "interaction":
            if drug_b_id is None:
                return StructuredFactResponse(
                    data={"found": False, "error": "drug_b_id is required for interaction lookup"},
                    source_type="structured",
                    drug_id=drug_id,
                )
            data = self._interactions.get_interaction(drug_id, drug_b_id)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        if qt == "patient_medications":
            if patient_id is None:
                return StructuredFactResponse(
                    data={"found": False, "error": "patient_id is required for patient medication lookup"},
                    source_type="structured",
                    drug_id=drug_id,
                )
            data = self._patient_meds.get_patient_medications(patient_id)
            return StructuredFactResponse(
                data=data, source_type="structured", drug_id=drug_id
            )

        # ----------------------------------------------------------------
        # Vector / RAG routes
        # ----------------------------------------------------------------
        if query_embedding is None:
            return RetrievalResponse(passages=[], source_type="vector")

        raw_results: list[dict[str, Any]] = self._vector_index.search(
            query_embedding=query_embedding,
            drug_id=drug_id,
            section_types=section_types or [],
            top_k=top_k,
        )

        passages = [
            RetrievalPassage(
                chunk_id=r.get("chunk_id", ""),
                section_type=r.get("section_type", ""),
                chunk_text=r.get("chunk_text", ""),
                score=float(r.get("score", 0.0)),
                source_url=r.get("source_url"),
            )
            for r in raw_results
        ]

        return RetrievalResponse(passages=passages, source_type="vector")
