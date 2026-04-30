from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.drug import DrugLabelSection


class DrugSectionsService:
    """Retrieves label sections for a given drug from the database."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_section(self, drug_id: str, section_type: str) -> Optional[dict[str, Any]]:
        """
        Retrieve a specific label section by drug_id and section_type.

        Returns a dict with section text and metadata, or None if not found.
        """
        section = (
            self._db.query(DrugLabelSection)
            .filter(
                DrugLabelSection.drug_id == drug_id,
                DrugLabelSection.section_type == section_type,
            )
            .order_by(DrugLabelSection.section_rank.asc().nullslast())
            .first()
        )

        if section is None:
            return None

        return {
            "found": True,
            "drug_id": drug_id,
            "section_id": section.id,
            "section_type": section.section_type,
            "section_title": section.section_title,
            "section_text": section.section_text,
            "source_url": section.source_url,
            "source_set_id": section.source_set_id,
            "source_system": section.source_system,
            "section_rank": section.section_rank,
            "source_type": "label_section",
        }

    def list_sections(self, drug_id: str) -> list[dict[str, Any]]:
        """List all available section types for a drug."""
        sections = (
            self._db.query(DrugLabelSection)
            .filter(DrugLabelSection.drug_id == drug_id)
            .order_by(DrugLabelSection.section_rank.asc().nullslast())
            .all()
        )

        return [
            {
                "section_id": s.id,
                "section_type": s.section_type,
                "section_title": s.section_title,
                "section_rank": s.section_rank,
                "source_type": "label_section",
            }
            for s in sections
        ]
