from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.drug import DrugInteraction


class InteractionService:
    """Retrieves drug-drug interaction data from the database."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_interaction(self, drug_a_id: str, drug_b_id: str) -> dict[str, Any]:
        """
        Look up the interaction between two drugs.

        The query is order-insensitive: checks both (a, b) and (b, a) orderings.
        Returns a dict with found=True and interaction data, or found=False.
        """
        interaction = (
            self._db.query(DrugInteraction)
            .filter(
                or_(
                    (DrugInteraction.drug_a_id == drug_a_id) & (DrugInteraction.drug_b_id == drug_b_id),
                    (DrugInteraction.drug_a_id == drug_b_id) & (DrugInteraction.drug_b_id == drug_a_id),
                )
            )
            .first()
        )

        if interaction is None:
            return {
                "found": False,
                "drug_a_id": drug_a_id,
                "drug_b_id": drug_b_id,
                "source_type": "structured",
            }

        return {
            "found": True,
            "interaction_id": interaction.id,
            "drug_a_id": interaction.drug_a_id,
            "drug_b_id": interaction.drug_b_id,
            "severity": interaction.severity,
            "plain_language_summary": interaction.plain_language_summary,
            "technical_summary": interaction.technical_summary,
            "mechanism_summary": interaction.mechanism_summary,
            "source_url": interaction.source_url,
            "source_system": interaction.source_system,
            "source_type": "structured",
        }

    def get_interactions_for_drug(self, drug_id: str) -> list[dict[str, Any]]:
        """Return all interactions involving a given drug (either as drug_a or drug_b)."""
        interactions = (
            self._db.query(DrugInteraction)
            .filter(
                or_(
                    DrugInteraction.drug_a_id == drug_id,
                    DrugInteraction.drug_b_id == drug_id,
                )
            )
            .all()
        )

        return [
            {
                "found": True,
                "interaction_id": i.id,
                "drug_a_id": i.drug_a_id,
                "drug_b_id": i.drug_b_id,
                "severity": i.severity,
                "plain_language_summary": i.plain_language_summary,
                "technical_summary": i.technical_summary,
                "mechanism_summary": i.mechanism_summary,
                "source_url": i.source_url,
                "source_system": i.source_system,
                "source_type": "structured",
            }
            for i in interactions
        ]
