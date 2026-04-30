from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.drug import PatientMedication


class PatientMedService:
    """Retrieves patient medication records from the database."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_patient_medications(
        self, patient_id: str, active_only: bool = True
    ) -> dict[str, Any]:
        """
        Return all medication records for a given patient.

        If active_only=True, filters to records where active_flag is True.
        """
        query = self._db.query(PatientMedication).filter(
            PatientMedication.patient_id == patient_id
        )

        if active_only:
            query = query.filter(PatientMedication.active_flag == True)  # noqa: E712

        medications = query.order_by(PatientMedication.created_at.desc()).all()

        return {
            "found": True,
            "patient_id": patient_id,
            "active_only": active_only,
            "count": len(medications),
            "medications": [
                {
                    "id": med.id,
                    "drug_id": med.drug_id,
                    "medication_name_as_recorded": med.medication_name_as_recorded,
                    "normalized_medication_name": med.normalized_medication_name,
                    "dose_text": med.dose_text,
                    "frequency_text": med.frequency_text,
                    "route_text": med.route_text,
                    "active_flag": med.active_flag,
                    "start_date": med.start_date.isoformat() if med.start_date else None,
                    "end_date": med.end_date.isoformat() if med.end_date else None,
                    "created_at": med.created_at.isoformat(),
                    "updated_at": med.updated_at.isoformat(),
                }
                for med in medications
            ],
            "source_type": "structured",
        }
