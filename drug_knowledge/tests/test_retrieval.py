"""
Tests for DrugFactsService and InteractionService retrieval functions.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models.drug import Drug, DrugInteraction, DrugStructuredFacts
from app.services.drug_facts import DrugFactsService
from app.services.interactions import InteractionService


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


def _drug_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def drug_with_facts(db: Session) -> tuple[Drug, DrugStructuredFacts]:
    drug = Drug(
        id=_drug_id(),
        generic_name="Metformin",
        normalized_generic_name="metformin",
        brand_names=["Glucophage"],
        active_ingredients=["Metformin HCl"],
        drug_classes=["Biguanide"],
        dosage_forms=["Tablet"],
        routes=["Oral"],
        source_set_id="test-set-id-metformin",
    )
    db.add(drug)
    db.flush()

    facts = DrugStructuredFacts(
        id=_drug_id(),
        drug_id=drug.id,
        plain_language_purpose="Metformin lowers blood sugar in people with type 2 diabetes.",
        moderate_purpose="Metformin is a first-line treatment for type 2 diabetes mellitus.",
        technical_purpose=(
            "Metformin hydrochloride is a biguanide antihyperglycemic agent used in the "
            "management of type 2 diabetes mellitus."
        ),
        common_indications=["Type 2 Diabetes"],
        common_side_effects=["Nausea", "Diarrhea", "Vomiting", "Flatulence"],
        serious_side_effects=["Lactic acidosis"],
        boxed_warning_flag=True,
        boxed_warning_summary="Lactic acidosis risk; contraindicated in renal impairment.",
        contraindication_summary="Contraindicated in patients with eGFR < 30.",
        warnings_precautions_summary="Monitor renal function; hold before contrast media.",
        pregnancy_summary="Category B — no adequate studies in pregnant women.",
        breastfeeding_summary="Metformin is excreted in breast milk.",
        renal_summary="Contraindicated when eGFR < 30 mL/min/1.73m2.",
        hepatic_summary="Not recommended in hepatic impairment.",
        alcohol_summary="Avoid excessive alcohol.",
        food_interaction_summary="Take with food to reduce GI side effects.",
        monitoring_summary="Monitor HbA1c, renal function periodically.",
    )
    db.add(facts)
    db.commit()
    return drug, facts


@pytest.fixture
def two_drugs_with_interaction(db: Session) -> tuple[Drug, Drug, DrugInteraction]:
    drug_a = Drug(
        id=_drug_id(),
        generic_name="Warfarin",
        normalized_generic_name="warfarin",
        brand_names=["Coumadin"],
        active_ingredients=[],
        drug_classes=[],
        dosage_forms=[],
        routes=[],
        source_set_id="test-set-warfarin",
    )
    drug_b = Drug(
        id=_drug_id(),
        generic_name="Aspirin",
        normalized_generic_name="aspirin",
        brand_names=[],
        active_ingredients=[],
        drug_classes=[],
        dosage_forms=[],
        routes=[],
        source_set_id="test-set-aspirin",
    )
    db.add(drug_a)
    db.add(drug_b)
    db.flush()

    interaction = DrugInteraction(
        id=_drug_id(),
        drug_a_id=drug_a.id,
        drug_b_id=drug_b.id,
        severity="major",
        plain_language_summary="Taking warfarin and aspirin together increases bleeding risk.",
        technical_summary="Aspirin inhibits platelet aggregation and may displace warfarin from protein binding.",
        mechanism_summary="Pharmacodynamic and pharmacokinetic interaction.",
        source_system="test",
    )
    db.add(interaction)
    db.commit()
    return drug_a, drug_b, interaction


# ---------------------------------------------------------------------------
# DrugFactsService tests
# ---------------------------------------------------------------------------


def test_get_drug_purpose_low_literacy(drug_with_facts: tuple) -> None:
    drug, facts = drug_with_facts
    # We need the db session; get it from the drug's session
    from sqlalchemy.orm import object_session

    db = object_session(drug)
    svc = DrugFactsService(db)

    result = svc.get_drug_purpose(drug.id, literacy_level="low")

    assert result["found"] is True
    assert result["drug_id"] == drug.id
    assert result["literacy_level"] == "low"
    # Low literacy should return plain_language_purpose first
    assert result["purpose"] == facts.plain_language_purpose
    assert result["source_type"] == "structured"


def test_get_drug_purpose_fallback(drug_with_facts: tuple) -> None:
    """If moderate_purpose is None, should fall back to plain_language_purpose."""
    drug, facts = drug_with_facts
    from sqlalchemy.orm import object_session

    db = object_session(drug)

    # Temporarily set moderate_purpose to None
    facts.moderate_purpose = None
    db.flush()

    svc = DrugFactsService(db)
    result = svc.get_drug_purpose(drug.id, literacy_level="moderate")

    assert result["found"] is True
    # Should fall back to plain_language_purpose
    assert result["purpose"] == facts.plain_language_purpose


def test_get_drug_purpose_high_literacy(drug_with_facts: tuple) -> None:
    drug, facts = drug_with_facts
    from sqlalchemy.orm import object_session

    db = object_session(drug)
    svc = DrugFactsService(db)

    result = svc.get_drug_purpose(drug.id, literacy_level="high")

    assert result["found"] is True
    # High literacy: technical_purpose first
    assert result["purpose"] == facts.technical_purpose


def test_get_common_side_effects(drug_with_facts: tuple) -> None:
    drug, facts = drug_with_facts
    from sqlalchemy.orm import object_session

    db = object_session(drug)
    svc = DrugFactsService(db)

    result = svc.get_common_side_effects(drug.id)

    assert result["found"] is True
    assert result["drug_id"] == drug.id
    assert "Nausea" in result["common_side_effects"]
    assert result["source_type"] == "structured"


def test_get_serious_side_effects_with_boxed_warning(drug_with_facts: tuple) -> None:
    drug, facts = drug_with_facts
    from sqlalchemy.orm import object_session

    db = object_session(drug)
    svc = DrugFactsService(db)

    result = svc.get_serious_side_effects(drug.id)

    assert result["found"] is True
    assert result["boxed_warning_flag"] is True
    assert "Lactic acidosis" in result["serious_side_effects"]
    assert result["boxed_warning_summary"] is not None
    assert result["source_type"] == "structured"


def test_get_drug_facts_not_found(db: Session) -> None:
    svc = DrugFactsService(db)
    result = svc.get_drug_basic_profile("nonexistent-id")

    assert result["found"] is False
    assert result["drug_id"] == "nonexistent-id"


# ---------------------------------------------------------------------------
# InteractionService tests
# ---------------------------------------------------------------------------


def test_get_interaction_found(two_drugs_with_interaction: tuple) -> None:
    drug_a, drug_b, interaction = two_drugs_with_interaction
    from sqlalchemy.orm import object_session

    db = object_session(drug_a)
    svc = InteractionService(db)

    result = svc.get_interaction(drug_a.id, drug_b.id)

    assert result["found"] is True
    assert result["severity"] == "major"
    assert result["source_type"] == "structured"


def test_get_interaction_order_insensitive(two_drugs_with_interaction: tuple) -> None:
    """Looking up (b, a) should return the same result as (a, b)."""
    drug_a, drug_b, interaction = two_drugs_with_interaction
    from sqlalchemy.orm import object_session

    db = object_session(drug_a)
    svc = InteractionService(db)

    result_ab = svc.get_interaction(drug_a.id, drug_b.id)
    result_ba = svc.get_interaction(drug_b.id, drug_a.id)

    assert result_ab["found"] is True
    assert result_ba["found"] is True
    assert result_ab["interaction_id"] == result_ba["interaction_id"]


def test_get_interaction_not_found(db: Session) -> None:
    svc = InteractionService(db)
    result = svc.get_interaction("drug-a-id", "drug-b-id")

    assert result["found"] is False
