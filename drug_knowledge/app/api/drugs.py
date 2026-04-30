from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.drug import DrugRead, DrugResolutionResult
from app.services.drug_facts import DrugFactsService
from app.services.drug_resolution import DrugResolutionService
from app.services.drug_sections import DrugSectionsService
from app.services.patient_meds import PatientMedService

router = APIRouter(prefix="/drugs", tags=["drugs"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def get_resolution_service(db: Session = Depends(get_db)) -> DrugResolutionService:
    return DrugResolutionService(db)


def get_facts_service(db: Session = Depends(get_db)) -> DrugFactsService:
    return DrugFactsService(db)


def get_sections_service(db: Session = Depends(get_db)) -> DrugSectionsService:
    return DrugSectionsService(db)


def get_patient_med_service(db: Session = Depends(get_db)) -> PatientMedService:
    return PatientMedService(db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/resolve", response_model=DrugResolutionResult)
def resolve_drug(
    q: Annotated[str, Query(description="Drug name to resolve")],
    svc: DrugResolutionService = Depends(get_resolution_service),
) -> DrugResolutionResult:
    """Resolve a free-text drug name to a canonical drug record."""
    return svc.resolve_drug(q)


@router.get("/resolve-many", response_model=list[DrugResolutionResult])
def resolve_multiple_drugs(
    q: Annotated[list[str], Query(description="List of drug names to resolve")],
    svc: DrugResolutionService = Depends(get_resolution_service),
) -> list[DrugResolutionResult]:
    """Resolve multiple drug names at once."""
    return svc.resolve_multiple_drugs(q)


@router.get("/{drug_id}/profile")
def get_drug_profile(
    drug_id: str,
    svc: DrugFactsService = Depends(get_facts_service),
) -> dict:
    """Return basic profile information for a drug."""
    result = svc.get_drug_basic_profile(drug_id)
    if not result.get("found", True):
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")
    return result


@router.get("/{drug_id}/purpose")
def get_drug_purpose(
    drug_id: str,
    literacy_level: Annotated[str, Query(description="one of: low, moderate, high")] = "moderate",
    svc: DrugFactsService = Depends(get_facts_service),
) -> dict:
    """Return the drug's purpose at the specified literacy level."""
    result = svc.get_drug_purpose(drug_id, literacy_level)
    if not result.get("found", True):
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")
    return result


@router.get("/{drug_id}/side-effects/common")
def get_common_side_effects(
    drug_id: str,
    svc: DrugFactsService = Depends(get_facts_service),
) -> dict:
    """Return common side effects for a drug."""
    result = svc.get_common_side_effects(drug_id)
    if not result.get("found", True):
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")
    return result


@router.get("/{drug_id}/side-effects/serious")
def get_serious_side_effects(
    drug_id: str,
    svc: DrugFactsService = Depends(get_facts_service),
) -> dict:
    """Return serious side effects and boxed warning info for a drug."""
    result = svc.get_serious_side_effects(drug_id)
    if not result.get("found", True):
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")
    return result


@router.get("/{drug_id}/contraindications")
def get_contraindications(
    drug_id: str,
    svc: DrugFactsService = Depends(get_facts_service),
) -> dict:
    """Return contraindication summary for a drug."""
    result = svc.get_contraindication_summary(drug_id)
    if not result.get("found", True):
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")
    return result


@router.get("/{drug_id}/warnings")
def get_warnings(
    drug_id: str,
    svc: DrugFactsService = Depends(get_facts_service),
) -> dict:
    """Return warnings and precautions for a drug."""
    result = svc.get_warning_summary(drug_id)
    if not result.get("found", True):
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")
    return result


@router.get("/{drug_id}/populations/{population_type}")
def get_special_population(
    drug_id: str,
    population_type: str,
    svc: DrugFactsService = Depends(get_facts_service),
) -> dict:
    """Return special population guidance (pregnancy, breastfeeding, renal, hepatic)."""
    result = svc.get_special_population_summary(drug_id, population_type)
    if not result.get("found", True):
        raise HTTPException(status_code=404, detail=f"Drug {drug_id} not found")
    return result


@router.get("/{drug_id}/sections/{section_type}")
def get_label_section(
    drug_id: str,
    section_type: str,
    svc: DrugSectionsService = Depends(get_sections_service),
) -> dict:
    """Return the raw label section text for a drug."""
    result = svc.get_section(drug_id, section_type)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Section '{section_type}' not found for drug {drug_id}",
        )
    return result


@router.get("/{drug_id}/sections")
def list_label_sections(
    drug_id: str,
    svc: DrugSectionsService = Depends(get_sections_service),
) -> list[dict]:
    """List all available label sections for a drug."""
    return svc.list_sections(drug_id)


@router.get("/patients/{patient_id}/medications")
def get_patient_medications(
    patient_id: str,
    active_only: bool = True,
    svc: PatientMedService = Depends(get_patient_med_service),
) -> dict:
    """Return medications recorded for a patient."""
    return svc.get_patient_medications(patient_id, active_only=active_only)
