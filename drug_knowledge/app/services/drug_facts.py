from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.drug import Drug, DrugStructuredFacts


class DrugFactsService:
    """Deterministic retrieval of structured drug facts from the database."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_drug(self, drug_id: str) -> Drug | None:
        return self._db.query(Drug).filter(Drug.id == drug_id).first()

    def _get_facts(self, drug_id: str) -> DrugStructuredFacts | None:
        return (
            self._db.query(DrugStructuredFacts)
            .filter(DrugStructuredFacts.drug_id == drug_id)
            .first()
        )

    def _not_found(self, drug_id: str, field: str) -> dict[str, Any]:
        return {
            "found": False,
            "drug_id": drug_id,
            "field": field,
            "source_type": "structured",
        }

    # ------------------------------------------------------------------
    # Public retrieval methods
    # ------------------------------------------------------------------

    def get_drug_basic_profile(self, drug_id: str) -> dict[str, Any]:
        drug = self._get_drug(drug_id)
        if drug is None:
            return self._not_found(drug_id, "basic_profile")
        return {
            "found": True,
            "drug_id": drug.id,
            "generic_name": drug.generic_name,
            "normalized_generic_name": drug.normalized_generic_name,
            "brand_names": drug.brand_names or [],
            "manufacturer_name": drug.manufacturer_name,
            "labeler_name": drug.labeler_name,
            "active_ingredients": drug.active_ingredients or [],
            "drug_classes": drug.drug_classes or [],
            "dosage_forms": drug.dosage_forms or [],
            "routes": drug.routes or [],
            "source_set_id": drug.source_set_id,
            "source_system": drug.source_system,
            "source_url": drug.source_url,
            "last_label_update": drug.last_label_update.isoformat() if drug.last_label_update else None,
            "source_type": "structured",
        }

    def get_drug_purpose(self, drug_id: str, literacy_level: str = "moderate") -> dict[str, Any]:
        """
        Return the drug purpose at the requested literacy level.

        Fallback chains:
          high:     technical → moderate → plain
          moderate: moderate  → plain    → technical
          low:      plain     → moderate (no technical fallback)
        """
        drug = self._get_drug(drug_id)
        if drug is None:
            return self._not_found(drug_id, "purpose")

        facts = self._get_facts(drug_id)
        if facts is None:
            return self._not_found(drug_id, "purpose")

        level = (literacy_level or "moderate").lower()

        if level == "high":
            purpose = facts.technical_purpose or facts.moderate_purpose or facts.plain_language_purpose
        elif level == "low":
            purpose = facts.plain_language_purpose or facts.moderate_purpose
        else:  # moderate (default)
            purpose = facts.moderate_purpose or facts.plain_language_purpose or facts.technical_purpose

        return {
            "found": True,
            "drug_id": drug_id,
            "literacy_level": level,
            "purpose": purpose,
            "common_indications": facts.common_indications or [],
            "source_type": "structured",
        }

    def get_common_side_effects(self, drug_id: str) -> dict[str, Any]:
        facts = self._get_facts(drug_id)
        if facts is None:
            return self._not_found(drug_id, "common_side_effects")
        return {
            "found": True,
            "drug_id": drug_id,
            "common_side_effects": facts.common_side_effects or [],
            "source_type": "structured",
        }

    def get_serious_side_effects(self, drug_id: str) -> dict[str, Any]:
        facts = self._get_facts(drug_id)
        if facts is None:
            return self._not_found(drug_id, "serious_side_effects")
        return {
            "found": True,
            "drug_id": drug_id,
            "serious_side_effects": facts.serious_side_effects or [],
            "boxed_warning_flag": facts.boxed_warning_flag,
            "boxed_warning_summary": facts.boxed_warning_summary,
            "source_type": "structured",
        }

    def get_contraindication_summary(self, drug_id: str) -> dict[str, Any]:
        facts = self._get_facts(drug_id)
        if facts is None:
            return self._not_found(drug_id, "contraindication_summary")
        return {
            "found": True,
            "drug_id": drug_id,
            "contraindication_summary": facts.contraindication_summary,
            "source_type": "structured",
        }

    def get_warning_summary(self, drug_id: str) -> dict[str, Any]:
        facts = self._get_facts(drug_id)
        if facts is None:
            return self._not_found(drug_id, "warning_summary")
        return {
            "found": True,
            "drug_id": drug_id,
            "warnings_precautions_summary": facts.warnings_precautions_summary,
            "boxed_warning_flag": facts.boxed_warning_flag,
            "boxed_warning_summary": facts.boxed_warning_summary,
            "alcohol_summary": facts.alcohol_summary,
            "food_interaction_summary": facts.food_interaction_summary,
            "monitoring_summary": facts.monitoring_summary,
            "source_type": "structured",
        }

    def get_special_population_summary(self, drug_id: str, population_type: str) -> dict[str, Any]:
        """
        Return special population guidance.

        population_type values: "pregnancy", "breastfeeding", "renal", "hepatic"
        """
        facts = self._get_facts(drug_id)
        if facts is None:
            return self._not_found(drug_id, f"special_population_{population_type}")

        pop = (population_type or "").lower()
        population_map: dict[str, str | None] = {
            "pregnancy": facts.pregnancy_summary,
            "breastfeeding": facts.breastfeeding_summary,
            "renal": facts.renal_summary,
            "hepatic": facts.hepatic_summary,
        }

        summary = population_map.get(pop)
        return {
            "found": True,
            "drug_id": drug_id,
            "population_type": pop,
            "summary": summary,
            "source_type": "structured",
        }
