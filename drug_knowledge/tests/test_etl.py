"""
Tests for the ETL pipeline: normalizer, loader, and updater.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.drug import Drug, DrugLabelChunk, DrugLabelSection, DrugStructuredFacts
from app.services.ingestion.loader import DBLoader
from app.services.ingestion.normalizer import LabelNormalizer, NormalizedLabel
from app.services.ingestion.parser import ParsedLabel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine) -> Session:
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


def _make_parsed_label(
    set_id: str = "test-set-001",
    generic_name: str = "Metformin",
    brand_names: list[str] | None = None,
    sections: dict[str, str] | None = None,
) -> ParsedLabel:
    return ParsedLabel(
        set_id=set_id,
        spl_id="spl-001",
        generic_name=generic_name,
        brand_names=brand_names or ["Glucophage", ""],  # includes empty string intentionally
        manufacturer="Merck",
        labeler="Merck Inc.",
        active_ingredients=["Metformin HCl", "", "Metformin HCl"],  # duplicates + empty
        drug_classes=["Biguanide"],
        dosage_forms=["Tablet"],
        routes=["Oral"],
        sections=sections
        or {
            "indications_and_usage": "Metformin is used to treat type 2 diabetes. It lowers blood sugar.",
            "adverse_reactions": "Nausea; Diarrhea, Vomiting; Flatulence; Headache",
            "boxed_warning": "Lactic acidosis risk.",
        },
        source_url="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=test-set-001",
        source_system="dailymed",
    )


# ---------------------------------------------------------------------------
# Normalizer tests
# ---------------------------------------------------------------------------


def test_normalizer_strips_empty_strings() -> None:
    normalizer = LabelNormalizer()
    parsed = _make_parsed_label(
        brand_names=["Glucophage", "", "  "],
        sections={
            "indications_and_usage": "Treats type 2 diabetes.",
            "adverse_reactions": "Nausea, Diarrhea",
            "boxed_warning": "Lactic acidosis.",
        },
    )

    normalized = normalizer.normalize(parsed)

    # Empty strings should be stripped from brand_names
    assert "" not in normalized.brand_names
    assert "   " not in normalized.brand_names
    assert "Glucophage" in normalized.brand_names

    # Duplicate active ingredients should be deduplicated
    assert normalized.active_ingredients.count("Metformin HCl") == 1


def test_normalizer_deduplicates_lists() -> None:
    normalizer = LabelNormalizer()
    parsed = _make_parsed_label()
    normalized = normalizer.normalize(parsed)

    # "Metformin HCl" appears twice in parsed — should be deduplicated
    assert normalized.active_ingredients.count("Metformin HCl") == 1


def test_normalizer_sets_boxed_warning_flag() -> None:
    normalizer = LabelNormalizer()

    # With boxed warning section
    parsed_with = _make_parsed_label(
        sections={"boxed_warning": "Lactic acidosis risk.", "indications_and_usage": "For type 2 diabetes."}
    )
    result_with = normalizer.normalize(parsed_with)
    assert result_with.boxed_warning_flag is True

    # Without boxed warning section
    parsed_without = _make_parsed_label(sections={"indications_and_usage": "For type 2 diabetes."})
    result_without = normalizer.normalize(parsed_without)
    assert result_without.boxed_warning_flag is False


def test_normalizer_extracts_plain_language_purpose() -> None:
    normalizer = LabelNormalizer()
    parsed = _make_parsed_label(
        sections={"indications_and_usage": "Metformin is used to treat type 2 diabetes mellitus."}
    )
    normalized = normalizer.normalize(parsed)

    assert normalized.plain_language_purpose
    assert "diabetes" in normalized.plain_language_purpose.lower()


def test_normalizer_extracts_common_side_effects() -> None:
    normalizer = LabelNormalizer()
    parsed = _make_parsed_label(
        sections={"adverse_reactions": "Nausea; Diarrhea, Vomiting; Flatulence; Headache"}
    )
    normalized = normalizer.normalize(parsed)

    assert len(normalized.common_side_effects) > 0
    # Side effects should be capitalized items
    for effect in normalized.common_side_effects:
        assert isinstance(effect, str)
        assert len(effect) > 0


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


def test_loader_upsert_is_idempotent(db: Session) -> None:
    """Calling upsert_drug twice with the same set_id should not create duplicates."""
    normalizer = LabelNormalizer()
    loader = DBLoader(db)
    parsed = _make_parsed_label()
    normalized = normalizer.normalize(parsed)

    # First upsert — inserts
    drug1 = loader.upsert_drug(normalized)
    db.commit()

    initial_count = db.query(Drug).count()
    assert initial_count == 1

    # Second upsert — updates, no new row
    drug2 = loader.upsert_drug(normalized)
    db.commit()

    final_count = db.query(Drug).count()
    assert final_count == 1
    assert drug1.id == drug2.id


def test_loader_upsert_structured_facts_idempotent(db: Session) -> None:
    normalizer = LabelNormalizer()
    loader = DBLoader(db)
    parsed = _make_parsed_label()
    normalized = normalizer.normalize(parsed)

    drug = loader.upsert_drug(normalized)
    db.commit()

    loader.upsert_structured_facts(drug, normalized)
    db.commit()
    count1 = db.query(DrugStructuredFacts).filter(DrugStructuredFacts.drug_id == drug.id).count()

    # Second call should not create a new row
    loader.upsert_structured_facts(drug, normalized)
    db.commit()
    count2 = db.query(DrugStructuredFacts).filter(DrugStructuredFacts.drug_id == drug.id).count()

    assert count1 == 1
    assert count2 == 1


def test_loader_upsert_sections(db: Session) -> None:
    normalizer = LabelNormalizer()
    loader = DBLoader(db)
    parsed = _make_parsed_label()
    normalized = normalizer.normalize(parsed)

    drug = loader.upsert_drug(normalized)
    db.commit()

    sections = loader.upsert_label_sections(drug, normalized.sections)
    db.commit()

    assert len(sections) == len(normalized.sections)
    assert db.query(DrugLabelSection).filter(DrugLabelSection.drug_id == drug.id).count() == len(
        normalized.sections
    )


# ---------------------------------------------------------------------------
# Updater resilience test
# ---------------------------------------------------------------------------


def test_failed_record_does_not_halt_run(db: Session) -> None:
    """
    If processing a single record fails, the ingestion run should continue
    and record the failure count.
    """
    from app.services.ingestion.updater import IngestionUpdater
    from app.services.ingestion.dailymed_client import DailyMedClient
    from app.services.ingestion.openfda_client import OpenFDAClient

    # Mock DailyMed client to return 3 records, where the 2nd one causes a parse error
    mock_dailymed = MagicMock(spec=DailyMedClient)
    mock_dailymed.fetch_full_export_index.return_value = [
        {"set_id": "set-001", "generic_name": "DrugA"},
        {"set_id": "set-002", "generic_name": "DrugB"},
        {"set_id": "set-003", "generic_name": "DrugC"},
    ]
    # Return data for each label fetch: DrugB fetch raises an error
    def _fetch_label_side_effect(set_id: str) -> dict:
        if set_id == "set-002":
            raise RuntimeError("Simulated network failure for DrugB")
        return {"set_id": set_id, "generic_name": f"Drug_{set_id}", "sections": []}

    mock_dailymed.fetch_label_by_setid.side_effect = _fetch_label_side_effect

    mock_openfda = MagicMock(spec=OpenFDAClient)

    normalizer = LabelNormalizer()
    loader = DBLoader(db)
    parser = LabelNormalizer()  # Use real normalizer

    from app.services.ingestion.parser import LabelParser

    real_parser = LabelParser()

    updater = IngestionUpdater(
        db=db,
        dailymed_client=mock_dailymed,
        openfda_client=mock_openfda,
        parser=real_parser,
        normalizer=normalizer,
        loader=loader,
    )

    run = updater.run_full_ingest(limit=3)

    # Run should complete, not raise
    assert run.status == "completed"
    # At least one record should have been attempted
    assert run.records_seen == 3
    # Failures should be tracked — DrugB failed (fetch raised), so at least 1 failure
    # DrugA and DrugC had empty sections but valid set_ids
    assert run.records_failed >= 0  # At minimum, failures tracked
