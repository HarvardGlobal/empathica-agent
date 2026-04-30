from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

try:
    from sqlalchemy import JSON
except ImportError:
    from sqlalchemy.dialects.sqlite import JSON  # type: ignore[no-redef]

from app.db import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Drug(Base):
    __tablename__ = "drugs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    generic_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_generic_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    brand_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    manufacturer_name: Mapped[str] = mapped_column(String(512), nullable=True)
    labeler_name: Mapped[str] = mapped_column(String(512), nullable=True)
    active_ingredients: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    drug_classes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    dosage_forms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    routes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_set_id: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    source_spl_id: Mapped[str] = mapped_column(String(256), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=True)
    last_label_update: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    structured_facts: Mapped[list[DrugStructuredFacts]] = relationship(
        "DrugStructuredFacts", back_populates="drug", cascade="all, delete-orphan"
    )
    label_sections: Mapped[list[DrugLabelSection]] = relationship(
        "DrugLabelSection", back_populates="drug", cascade="all, delete-orphan"
    )
    label_chunks: Mapped[list[DrugLabelChunk]] = relationship(
        "DrugLabelChunk", back_populates="drug", cascade="all, delete-orphan"
    )
    patient_medications: Mapped[list[PatientMedication]] = relationship(
        "PatientMedication", back_populates="drug"
    )

    __table_args__ = (
        Index("ix_drugs_generic_name", "generic_name"),
        Index("ix_drugs_normalized_generic_name", "normalized_generic_name"),
    )


class DrugStructuredFacts(Base):
    __tablename__ = "drug_structured_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    drug_id: Mapped[str] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=False)
    plain_language_purpose: Mapped[str] = mapped_column(Text, nullable=True)
    moderate_purpose: Mapped[str] = mapped_column(Text, nullable=True)
    technical_purpose: Mapped[str] = mapped_column(Text, nullable=True)
    common_indications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    common_side_effects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    serious_side_effects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    boxed_warning_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    boxed_warning_summary: Mapped[str] = mapped_column(Text, nullable=True)
    contraindication_summary: Mapped[str] = mapped_column(Text, nullable=True)
    warnings_precautions_summary: Mapped[str] = mapped_column(Text, nullable=True)
    pregnancy_summary: Mapped[str] = mapped_column(Text, nullable=True)
    breastfeeding_summary: Mapped[str] = mapped_column(Text, nullable=True)
    renal_summary: Mapped[str] = mapped_column(Text, nullable=True)
    hepatic_summary: Mapped[str] = mapped_column(Text, nullable=True)
    alcohol_summary: Mapped[str] = mapped_column(Text, nullable=True)
    food_interaction_summary: Mapped[str] = mapped_column(Text, nullable=True)
    monitoring_summary: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    drug: Mapped[Drug] = relationship("Drug", back_populates="structured_facts")


class DrugLabelSection(Base):
    __tablename__ = "drug_label_sections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    drug_id: Mapped[str] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=False)
    section_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    section_title: Mapped[str] = mapped_column(String(512), nullable=True)
    section_text: Mapped[str] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=True)
    source_set_id: Mapped[str] = mapped_column(String(256), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=True)
    section_rank: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    drug: Mapped[Drug] = relationship("Drug", back_populates="label_sections")
    chunks: Mapped[list[DrugLabelChunk]] = relationship(
        "DrugLabelChunk", back_populates="section", cascade="all, delete-orphan"
    )


class DrugLabelChunk(Base):
    __tablename__ = "drug_label_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    drug_id: Mapped[str] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=False)
    section_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drug_label_sections.id"), nullable=False
    )
    section_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count_estimate: Mapped[int] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    drug: Mapped[Drug] = relationship("Drug", back_populates="label_chunks")
    section: Mapped[DrugLabelSection] = relationship("DrugLabelSection", back_populates="chunks")


class DrugInteraction(Base):
    __tablename__ = "drug_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    drug_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=False)
    drug_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("drugs.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(64), nullable=True)
    plain_language_summary: Mapped[str] = mapped_column(Text, nullable=True)
    technical_summary: Mapped[str] = mapped_column(Text, nullable=True)
    mechanism_summary: Mapped[str] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    drug_a: Mapped[Drug] = relationship("Drug", foreign_keys=[drug_a_id])
    drug_b: Mapped[Drug] = relationship("Drug", foreign_keys=[drug_b_id])


class PatientMedication(Base):
    __tablename__ = "patient_medications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    patient_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    drug_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drugs.id"), nullable=True
    )
    medication_name_as_recorded: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_medication_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    dose_text: Mapped[str] = mapped_column(String(256), nullable=True)
    frequency_text: Mapped[str] = mapped_column(String(256), nullable=True)
    route_text: Mapped[str] = mapped_column(String(256), nullable=True)
    active_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    drug: Mapped[Drug | None] = relationship("Drug", back_populates="patient_medications")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    run_type: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
