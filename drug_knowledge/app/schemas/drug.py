from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class DrugBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generic_name: str
    normalized_generic_name: str
    brand_names: list[str] = []
    manufacturer_name: Optional[str] = None
    labeler_name: Optional[str] = None
    active_ingredients: list[str] = []
    drug_classes: list[str] = []
    dosage_forms: list[str] = []
    routes: list[str] = []
    source_set_id: Optional[str] = None
    source_spl_id: Optional[str] = None
    source_system: Optional[str] = None
    source_url: Optional[str] = None
    last_label_update: Optional[datetime] = None


class DrugCreate(DrugBase):
    pass


class DrugRead(DrugBase):
    id: str
    created_at: datetime
    updated_at: datetime


class DrugStructuredFactsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drug_id: str
    plain_language_purpose: Optional[str] = None
    moderate_purpose: Optional[str] = None
    technical_purpose: Optional[str] = None
    common_indications: list[str] = []
    common_side_effects: list[str] = []
    serious_side_effects: list[str] = []
    boxed_warning_flag: bool = False
    boxed_warning_summary: Optional[str] = None
    contraindication_summary: Optional[str] = None
    warnings_precautions_summary: Optional[str] = None
    pregnancy_summary: Optional[str] = None
    breastfeeding_summary: Optional[str] = None
    renal_summary: Optional[str] = None
    hepatic_summary: Optional[str] = None
    alcohol_summary: Optional[str] = None
    food_interaction_summary: Optional[str] = None
    monitoring_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PatientMedicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_id: str
    drug_id: Optional[str] = None
    medication_name_as_recorded: str
    normalized_medication_name: str
    dose_text: Optional[str] = None
    frequency_text: Optional[str] = None
    route_text: Optional[str] = None
    active_flag: bool = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DrugInteractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drug_a_id: str
    drug_b_id: str
    severity: Optional[str] = None
    plain_language_summary: Optional[str] = None
    technical_summary: Optional[str] = None
    mechanism_summary: Optional[str] = None
    source_url: Optional[str] = None
    source_system: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_name: str
    run_type: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    records_seen: int
    records_inserted: int
    records_updated: int
    records_failed: int
    notes: Optional[str] = None


class DrugResolutionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    matched: bool
    drug_id: Optional[str] = None
    matched_name: Optional[str] = None
    match_type: Literal["exact_generic", "exact_brand", "alias", "fuzzy", "none"]
    confidence: float
    candidate_names: list[str] = []
