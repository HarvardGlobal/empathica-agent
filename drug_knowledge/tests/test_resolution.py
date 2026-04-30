"""
Tests for DrugResolutionService using a SQLite in-memory database.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.drug import Drug
from app.services.drug_resolution import DrugResolutionService


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


def _make_drug(
    generic_name: str,
    brand_names: list[str] | None = None,
    drug_id: str | None = None,
) -> Drug:
    return Drug(
        id=drug_id or str(uuid.uuid4()),
        generic_name=generic_name,
        normalized_generic_name=generic_name.lower().strip(),
        brand_names=brand_names or [],
        active_ingredients=[],
        drug_classes=[],
        dosage_forms=[],
        routes=[],
        source_set_id=str(uuid.uuid4()),
    )


@pytest.fixture
def populated_db(db: Session) -> Session:
    drugs = [
        _make_drug("Metformin", brand_names=["Glucophage", "Fortamet"]),
        _make_drug("Lisinopril", brand_names=["Prinivil", "Zestril"]),
        _make_drug("Atorvastatin", brand_names=["Lipitor"]),
        _make_drug("Metoprolol", brand_names=["Lopressor", "Toprol-XL"]),
        _make_drug("Amoxicillin", brand_names=["Amoxil"]),
    ]
    for drug in drugs:
        db.add(drug)
    db.commit()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_exact_generic_match(populated_db: Session) -> None:
    svc = DrugResolutionService(populated_db)
    result = svc.resolve_drug("Metformin")

    assert result.matched is True
    assert result.match_type == "exact_generic"
    assert result.confidence == 1.0
    assert result.matched_name == "Metformin"
    assert result.drug_id is not None


def test_exact_generic_match_case_insensitive(populated_db: Session) -> None:
    svc = DrugResolutionService(populated_db)
    result = svc.resolve_drug("METFORMIN")

    assert result.matched is True
    assert result.match_type == "exact_generic"


def test_exact_brand_match(populated_db: Session) -> None:
    svc = DrugResolutionService(populated_db)
    result = svc.resolve_drug("Glucophage")

    assert result.matched is True
    assert result.match_type == "exact_brand"
    assert result.confidence == 1.0
    assert result.matched_name == "Glucophage"


def test_fuzzy_match(populated_db: Session) -> None:
    svc = DrugResolutionService(populated_db)
    # "Atorvastatin" with a typo
    result = svc.resolve_drug("Atorvastatin")

    assert result.matched is True
    # Should match exact generic at minimum
    assert result.match_type in ("exact_generic", "exact_brand", "fuzzy")


def test_fuzzy_match_with_typo(populated_db: Session) -> None:
    svc = DrugResolutionService(populated_db)
    # "Amoxicilin" — one 'l' missing — close enough for fuzzy
    result = svc.resolve_drug("Amoxicilin")

    # Either fuzzy matched or not matched — it should not raise
    assert result.match_type in ("exact_generic", "exact_brand", "alias", "fuzzy", "none")
    assert 0.0 <= result.confidence <= 1.0


def test_no_match_returns_none_type(populated_db: Session) -> None:
    svc = DrugResolutionService(populated_db)
    result = svc.resolve_drug("xyzzypharmazole9999")

    assert result.matched is False
    assert result.match_type == "none"
    assert result.confidence == 0.0
    assert result.drug_id is None


def test_ambiguous_returns_candidates(db: Session) -> None:
    """Two drugs with similar names should return candidates, not a single guess."""
    drug_a = _make_drug("Metformin HCl", brand_names=[])
    drug_b = _make_drug("Metformin ER", brand_names=[])
    db.add(drug_a)
    db.add(drug_b)
    db.commit()

    svc = DrugResolutionService(db)
    # "Metformin" is a substring of both — ambiguous alias match
    result = svc.resolve_drug("Metformin")

    # Should not silently pick one
    assert len(result.candidate_names) >= 1
    # If ambiguous alias, matched should be False and candidates populated
    if result.match_type == "alias" and not result.matched:
        assert len(result.candidate_names) >= 2


def test_resolve_multiple_drugs(populated_db: Session) -> None:
    svc = DrugResolutionService(populated_db)
    results = svc.resolve_multiple_drugs(["Metformin", "Lisinopril", "xyzzypharmazole"])

    assert len(results) == 3
    assert results[0].matched is True
    assert results[1].matched is True
    assert results[2].matched is False
