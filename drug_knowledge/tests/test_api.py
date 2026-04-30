"""
Tests for the FastAPI endpoints using TestClient.
"""
from __future__ import annotations

import uuid
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models.drug import Drug, DrugStructuredFacts


# ---------------------------------------------------------------------------
# In-memory test DB setup
# ---------------------------------------------------------------------------


TEST_DB_URL = "sqlite:///./test_drug_api.db"


@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="module")
def test_session_factory(test_engine):
    return sessionmaker(bind=test_engine)


@pytest.fixture
def db(test_session_factory) -> Generator[Session, None, None]:
    session = test_session_factory()
    yield session
    session.close()


@pytest.fixture
def client(db: Session) -> TestClient:
    """Create a TestClient that overrides the DB dependency with the test session."""

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db
        finally:
            pass  # session closed by outer fixture

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_drug(db: Session, generic_name: str = "Metformin") -> Drug:
    drug = Drug(
        id=str(uuid.uuid4()),
        generic_name=generic_name,
        normalized_generic_name=generic_name.lower(),
        brand_names=["Glucophage"],
        active_ingredients=["Metformin HCl"],
        drug_classes=["Biguanide"],
        dosage_forms=["Tablet"],
        routes=["Oral"],
        source_set_id=str(uuid.uuid4()),
    )
    db.add(drug)

    facts = DrugStructuredFacts(
        id=str(uuid.uuid4()),
        drug_id=drug.id,
        plain_language_purpose="Lowers blood sugar for type 2 diabetes.",
        moderate_purpose="First-line treatment for type 2 diabetes mellitus.",
        technical_purpose="Biguanide antihyperglycemic agent.",
        common_indications=["Type 2 Diabetes"],
        common_side_effects=["Nausea", "Diarrhea"],
        serious_side_effects=["Lactic acidosis"],
        boxed_warning_flag=True,
        boxed_warning_summary="Risk of lactic acidosis.",
    )
    db.add(facts)
    db.commit()
    return drug


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_resolve_drug_returns_result(client: TestClient, db: Session) -> None:
    _make_drug(db, "Lisinopril")

    response = client.get("/drugs/resolve", params={"q": "Lisinopril"})
    assert response.status_code == 200

    data = response.json()
    assert "matched" in data
    assert "match_type" in data
    assert "confidence" in data
    assert "candidate_names" in data


def test_resolve_drug_no_match(client: TestClient) -> None:
    response = client.get("/drugs/resolve", params={"q": "xyzzypharmadelphine9999"})
    assert response.status_code == 200

    data = response.json()
    assert data["matched"] is False
    assert data["match_type"] == "none"


def test_drug_profile_found(client: TestClient, db: Session) -> None:
    drug = _make_drug(db, "Atorvastatin")
    response = client.get(f"/drugs/{drug.id}/profile")
    assert response.status_code == 200

    data = response.json()
    assert data["found"] is True
    assert data["generic_name"] == "Atorvastatin"
    assert data["source_type"] == "structured"


def test_drug_profile_404(client: TestClient) -> None:
    response = client.get("/drugs/nonexistent-drug-id/profile")
    assert response.status_code == 404


def test_drug_purpose_endpoint(client: TestClient, db: Session) -> None:
    drug = _make_drug(db, "Warfarin")
    response = client.get(f"/drugs/{drug.id}/purpose", params={"literacy_level": "low"})
    assert response.status_code == 200

    data = response.json()
    assert data["found"] is True
    assert data["literacy_level"] == "low"
    assert data["purpose"] is not None


def test_common_side_effects_endpoint(client: TestClient, db: Session) -> None:
    drug = _make_drug(db, "Aspirin")
    response = client.get(f"/drugs/{drug.id}/side-effects/common")
    assert response.status_code == 200

    data = response.json()
    assert data["found"] is True
    assert isinstance(data["common_side_effects"], list)


def test_serious_side_effects_endpoint(client: TestClient, db: Session) -> None:
    drug = _make_drug(db, "Ibuprofen")
    response = client.get(f"/drugs/{drug.id}/side-effects/serious")
    assert response.status_code == 200

    data = response.json()
    assert data["found"] is True
    assert "boxed_warning_flag" in data


def test_rag_retrieve_returns_passages(client: TestClient, db: Session) -> None:
    """
    Mock the embedder and vector index so the endpoint can be tested without
    actually running the model or ChromaDB.
    """
    drug = _make_drug(db, "Simvastatin")

    mock_embedding = [0.1] * 384  # all-MiniLM-L6-v2 produces 384-dim embeddings

    mock_passages = [
        {
            "chunk_id": str(uuid.uuid4()),
            "section_type": "indications_and_usage",
            "chunk_text": "Simvastatin is used to lower cholesterol.",
            "score": 0.95,
            "source_url": None,
        }
    ]

    with (
        patch(
            "app.api.retrieval._get_embedder"
        ) as mock_get_embedder,
        patch(
            "app.api.retrieval._get_vector_index"
        ) as mock_get_vector_index,
    ):
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = mock_embedding
        mock_get_embedder.return_value = mock_embedder

        mock_index = MagicMock()
        mock_index.search.return_value = mock_passages
        mock_get_vector_index.return_value = mock_index

        response = client.post(
            "/rag/retrieve",
            json={
                "query": "What is simvastatin used for?",
                "drug_id": drug.id,
                "section_types": ["indications_and_usage"],
                "top_k": 3,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["source_type"] == "vector"
    assert len(data["passages"]) == 1
    assert data["passages"][0]["chunk_text"] == "Simvastatin is used to lower cholesterol."
    assert data["passages"][0]["score"] == pytest.approx(0.95)
