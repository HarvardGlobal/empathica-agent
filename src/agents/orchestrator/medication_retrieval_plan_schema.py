from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

RiskLevel = Literal["low", "moderate", "high", "urgent", "unknown"]
Priority = Literal["required", "optional"]
MedicationScope = Literal["active_only", "active_and_recent", "all_available", "none"]
TargetType = Literal["explicit_user_drug", "patient_active_medication", "comparison_drug"]
ComparisonType = Literal[
    "asked_drug_vs_current_meds",
    "current_meds_side_effect_scan",
    "current_meds_interaction_scan",
    "current_meds_warning_scan",
    "none",
]


@dataclass
class ExplicitDrugMention:
    raw_mention: str
    normalized_name: str
    confidence: str
    reason: str


@dataclass
class MedicationLookupTarget:
    target_type: TargetType
    name: str
    identifier_type: str = "unknown"
    identifier_value: str = ""
    priority: Priority = "required"
    reason: str = ""


@dataclass
class FhirMedicationTarget:
    domain: str
    priority: Priority
    reason: str


@dataclass
class PatientMedicationScope:
    needed: bool
    scope: MedicationScope
    reason: str


@dataclass
class MedicationRetrievalPlan:
    intent: str
    question_type: str
    risk_level: RiskLevel
    requires_medication_evidence: bool
    requires_patient_medication_list: bool
    explicit_drugs_mentioned: list[ExplicitDrugMention] = field(default_factory=list)
    patient_medication_scope: PatientMedicationScope = field(
        default_factory=lambda: PatientMedicationScope(False, "none", "")
    )
    dailymed_lookup_targets: list[MedicationLookupTarget] = field(default_factory=list)
    fhir_medication_targets: list[FhirMedicationTarget] = field(default_factory=list)
    comparison_needed: bool = False
    comparison_type: ComparisonType = "none"
    missing_information_questions: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)
    planner_rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "question_type": self.question_type,
            "risk_level": self.risk_level,
            "requires_medication_evidence": self.requires_medication_evidence,
            "requires_patient_medication_list": self.requires_patient_medication_list,
            "explicit_drugs_mentioned": [asdict(item) for item in self.explicit_drugs_mentioned],
            "patient_medication_scope": asdict(self.patient_medication_scope),
            "dailymed_lookup_targets": [asdict(item) for item in self.dailymed_lookup_targets],
            "fhir_medication_targets": [asdict(item) for item in self.fhir_medication_targets],
            "comparison_needed": self.comparison_needed,
            "comparison_type": self.comparison_type,
            "missing_information_questions": self.missing_information_questions,
            "safety_flags": self.safety_flags,
            "planner_rationale": self.planner_rationale,
        }
