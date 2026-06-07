from __future__ import annotations

from google.genai import types

from src.tools.documents import document_ingestion as ingestion
from src.tools.documents import index_all_patient_documents as indexer
from src.tools.documents import patient_document_rag as rag


def test_extract_patient_id_from_nested_path():
    path = "patients/emily-wilson/oncology_notes/example.md"
    assert ingestion.extract_patient_id_from_source_path(path) == "emily-wilson"


def test_extract_patient_id_from_uploads_path():
    path = "patients/c0a80111-0000-4000-8000-000000000002/uploads/example.md"
    assert ingestion.extract_patient_id_from_source_path(path) == "c0a80111-0000-4000-8000-000000000002"


def test_ignore_keep_files():
    assert ingestion.is_supported_document("patients/emily/.keep") is False


def test_index_new_markdown_file(monkeypatch):
    class Blob:
        def __init__(self, name: str):
            self.name = name

    indexed = {}

    monkeypatch.setenv("PATIENT_DOCS_BUCKET", "bucket")
    monkeypatch.setenv("PATIENT_DOCS_PREFIX", "patients/")
    monkeypatch.setattr(indexer, "list_gcs_blobs", lambda bucket, prefix: [Blob("patients/emily-wilson/notes/example.md")])
    monkeypatch.setattr(indexer, "read_gcs_text", lambda bucket, path: "hello world from markdown")
    monkeypatch.setattr(indexer, "get_document_record", lambda source_path: None)
    monkeypatch.setattr(indexer, "embed_text", lambda text: [0.1, 0.2, 0.3])

    def fake_store(document_record, chunks):
        indexed["document_record"] = document_record
        indexed["chunks"] = chunks
        return document_record["document_id"]

    monkeypatch.setattr(indexer, "store_document_and_chunks", fake_store)
    monkeypatch.setattr(indexer, "write_indexing_run", lambda summary: summary["run_id"])

    indexer.main()

    assert indexed["document_record"]["patient_id"] == "emily-wilson"
    assert indexed["document_record"]["indexed"] is True
    assert indexed["chunks"][0]["patient_id"] == "emily-wilson"
    assert indexed["chunks"][0]["chunk_text"] == "hello world from markdown"


def test_skip_unchanged_indexed_file(monkeypatch):
    class Blob:
        def __init__(self, name: str):
            self.name = name

    calls = {"store": 0}

    monkeypatch.setenv("PATIENT_DOCS_BUCKET", "bucket")
    monkeypatch.setenv("PATIENT_DOCS_PREFIX", "patients/")
    monkeypatch.setattr(indexer, "list_gcs_blobs", lambda bucket, prefix: [Blob("patients/emily-wilson/notes/example.md")])
    monkeypatch.setattr(indexer, "read_gcs_text", lambda bucket, path: "same content")
    monkeypatch.setattr(indexer, "get_document_record", lambda source_path: {
        "document_id": "doc-1",
        "source_path": source_path,
        "content_hash": ingestion.content_hash("same content"),
        "embedding_model": "gemini-embedding-001",
        "indexed": True,
    })
    monkeypatch.setattr(indexer, "store_document_and_chunks", lambda *args, **kwargs: calls.__setitem__("store", calls["store"] + 1))
    monkeypatch.setattr(indexer, "write_indexing_run", lambda summary: summary["run_id"])

    indexer.main()

    assert calls["store"] == 0


def test_reindex_when_hash_changes(monkeypatch):
    class Blob:
        def __init__(self, name: str):
            self.name = name

    calls = {"store": 0, "content_hash": None}

    monkeypatch.setenv("PATIENT_DOCS_BUCKET", "bucket")
    monkeypatch.setenv("PATIENT_DOCS_PREFIX", "patients/")
    monkeypatch.setattr(indexer, "list_gcs_blobs", lambda bucket, prefix: [Blob("patients/emily-wilson/notes/example.md")])
    monkeypatch.setattr(indexer, "read_gcs_text", lambda bucket, path: "changed content")
    monkeypatch.setattr(indexer, "get_document_record", lambda source_path: {
        "document_id": "doc-1",
        "source_path": source_path,
        "content_hash": ingestion.content_hash("same content"),
        "embedding_model": "gemini-embedding-001",
        "indexed": True,
    })
    monkeypatch.setattr(indexer, "embed_text", lambda text: [0.1, 0.2, 0.3])

    def fake_store(document_record, chunks):
        calls["store"] += 1
        calls["content_hash"] = document_record["content_hash"]
        assert chunks[0]["patient_id"] == "emily-wilson"

    monkeypatch.setattr(indexer, "store_document_and_chunks", fake_store)
    monkeypatch.setattr(indexer, "write_indexing_run", lambda summary: summary["run_id"])

    indexer.main()

    assert calls["store"] == 1
    assert calls["content_hash"] == ingestion.content_hash("changed content")


def test_runtime_retrieval_filters_patient_chunks(monkeypatch):
    def fake_query_patient_chunks(patient_id: str):
        assert patient_id == "emily"
        return [
            {
                "chunk_id": "e1",
                "document_id": "doc-e",
                "patient_id": "emily",
                "source_path": "patients/emily/notes.md",
                "file_name": "notes.md",
                "chunk_text": "Emily has nausea",
                "embedding": [1.0, 0.0],
            },
            {
                "chunk_id": "m1",
                "document_id": "doc-m",
                "patient_id": "mary",
                "source_path": "patients/mary/notes.md",
                "file_name": "notes.md",
                "chunk_text": "Mary has fatigue",
                "embedding": [0.0, 1.0],
            },
        ]

    monkeypatch.setattr(rag, "query_patient_chunks", fake_query_patient_chunks)
    monkeypatch.setattr(rag, "embed_text", lambda query: [1.0, 0.0])

    out = rag.retrieve_patient_document_context(patient_id="emily", query="What do my notes say?")

    assert out["retrieval_method"] == "firestore_vector"
    assert out["snippets"]
    assert all("mary" not in (snippet["source_path"] or "").lower() for snippet in out["snippets"])
    assert out["snippets"][0]["document_id"] == "doc-e"
    assert "Emily has nausea" in out["snippets"][0]["chunk_text"]


def test_runtime_retrieval_returns_missing_context_when_no_chunks(monkeypatch):
    monkeypatch.setattr(rag, "query_patient_chunks", lambda patient_id: [])

    out = rag.retrieve_patient_document_context(patient_id="emily", query="What do my notes say?")

    assert out["status"] == "unavailable"
    assert out["missing_document_context"]
    assert out["snippets"] == []


def test_emily_query_does_not_retrieve_mary_chunks(monkeypatch):
    def fake_query_patient_chunks(patient_id: str):
        assert patient_id == "emily"
        return [
            {
                "chunk_id": "e1",
                "document_id": "doc-e",
                "patient_id": "emily",
                "source_path": "patients/emily/notes.md",
                "file_name": "notes.md",
                "chunk_text": "Emily notes mention nausea and fatigue",
                "embedding": [1.0, 0.0],
            },
            {
                "chunk_id": "m1",
                "document_id": "doc-m",
                "patient_id": "mary",
                "source_path": "patients/mary/notes.md",
                "file_name": "notes.md",
                "chunk_text": "Mary notes mention fatigue",
                "embedding": [0.0, 1.0],
            },
        ]

    monkeypatch.setattr(rag, "query_patient_chunks", fake_query_patient_chunks)
    monkeypatch.setattr(rag, "embed_text", lambda query: [1.0, 0.0])

    out = rag.retrieve_patient_document_context(patient_id="emily", query="What do my notes say about nausea?")
    assert out["snippets"]
    assert all("mary" not in (snippet["source_path"] or "").lower() for snippet in out["snippets"])


def test_mary_query_does_not_retrieve_emily_chunks(monkeypatch):
    def fake_query_patient_chunks(patient_id: str):
        assert patient_id == "mary"
        return [
            {
                "chunk_id": "e1",
                "document_id": "doc-e",
                "patient_id": "emily",
                "source_path": "patients/emily/notes.md",
                "file_name": "notes.md",
                "chunk_text": "Emily notes mention nausea and fatigue",
                "embedding": [1.0, 0.0],
            },
            {
                "chunk_id": "m1",
                "document_id": "doc-m",
                "patient_id": "mary",
                "source_path": "patients/mary/notes.md",
                "file_name": "notes.md",
                "chunk_text": "Mary notes mention fatigue",
                "embedding": [0.0, 1.0],
            },
        ]

    monkeypatch.setattr(rag, "query_patient_chunks", fake_query_patient_chunks)
    monkeypatch.setattr(rag, "embed_text", lambda query: [0.0, 1.0])

    out = rag.retrieve_patient_document_context(patient_id="mary", query="What do my notes say about fatigue?")
    assert out["snippets"]
    assert all("emily" not in (snippet["source_path"] or "").lower() for snippet in out["snippets"])


def test_keyword_fallback_used_when_vector_retrieval_fails(monkeypatch):
    monkeypatch.setattr(rag, "query_patient_chunks", lambda patient_id: [{"patient_id": patient_id}])

    def blow_up(_):
        raise RuntimeError("embedding failed")

    monkeypatch.setattr(rag, "embed_text", blow_up)
    monkeypatch.setattr(
        rag,
        "build_patient_document_context",
        lambda selection, docs_prefix=None: "PATIENT-SPECIFIC DOCUMENT CONTEXT:\nSelected snippet",
    )

    out = rag.retrieve_patient_document_context(patient_id="emily", query="What do my notes say?")
    assert out["retrieval_method"] == "keyword_fallback"
    assert out["snippets"]
    assert "Selected snippet" in out["snippets"][0]["chunk_text"]


def test_fake_embeddings_are_not_used_silently(monkeypatch):
    from src.tools.documents import document_embedding as embedding

    monkeypatch.setenv("ALLOW_FAKE_EMBEDDINGS", "false")
    monkeypatch.setattr(embedding, "_load_model", lambda: None)

    try:
        embedding.embed_text("example")
    except RuntimeError as exc:
        assert "ALLOW_FAKE_EMBEDDINGS is false" in str(exc)
    else:
        raise AssertionError("embed_text should fail when the model is unavailable and fake embeddings are disabled")


def test_orchestrator_calls_document_rag_for_note_question(monkeypatch):
    from src.agents.orchestrator import fhir_context_executor as executor
    from src.agents.orchestrator.retrieval_plan_schema import PlanContextItem, RetrievalPlan

    plan = RetrievalPlan(
        intent="patient_notes",
        question_type="notes_summary",
        risk_level="moderate",
        requires_patient_specific_context=True,
        required_context=[PlanContextItem("unstructured_patient_notes", "Needed", "required")],
        optional_context=[],
    )
    calls = {}

    monkeypatch.setattr(
        executor,
        "retrieve_patient_document_context",
        lambda *, patient_id, query, top_k=5, docs_prefix=None: calls.setdefault(
            "doc_rag",
            {"patient_id": patient_id, "query": query, "docs_prefix": docs_prefix},
        )
        or {
            "status": "available",
            "retrieval_method": "firestore_vector",
            "patient_id": patient_id,
            "query": query,
            "snippets": [{"chunk_text": "note"}],
            "missing_document_context": [],
            "warnings": [],
            "source_trace": [],
            "summary": "note",
        },
    )

    out = executor.execute_retrieval_plan(
        plan,
        fhir_patient_id="fhir-123",
        document_patient_id="emily-wilson",
        docs_prefix="patients/emily-wilson/",
        user_message="What do my notes say about nausea?",
    )
    assert "unstructured_patient_notes" in out["domains"]
    assert "doc_rag" in calls
    assert calls["doc_rag"]["patient_id"] == "emily-wilson"


def test_orchestrator_does_not_call_document_rag_for_general_education(monkeypatch):
    from src.agents.orchestrator import fhir_context_executor as executor
    from src.agents.orchestrator.retrieval_plan_schema import RetrievalPlan

    plan = RetrievalPlan(
        intent="general_education",
        question_type="education",
        risk_level="low",
        requires_patient_specific_context=False,
        required_context=[],
        optional_context=[],
    )
    called = {"doc_rag": False}

    def fail_doc_rag(**kwargs):
        called["doc_rag"] = True
        raise AssertionError("should not be called")

    monkeypatch.setattr(executor, "retrieve_patient_document_context", fail_doc_rag)

    out = executor.execute_retrieval_plan(
        plan,
        fhir_patient_id="fhir-123",
        document_patient_id="emily-wilson",
        docs_prefix="patients/emily-wilson/",
        user_message="What is ibuprofen?",
    )
    assert out["domains"] == {}
    assert called["doc_rag"] is False


def test_identity_split_uses_distinct_fhir_and_document_ids(monkeypatch):
    from src.tools.patient import identity_map as imap
    from src.agents.orchestrator import chat_orchestrator as orch

    identity = imap.PatientIdentity(
        user_id="test_user",
        fhir_patient_id="fhir-123",
        document_patient_id="emily-wilson",
        document_docs_prefix="patients/emily-wilson/",
        status="active",
        tenant="default",
    )

    monkeypatch.setattr(orch, "resolve_patient_identity", lambda user_id: identity)

    captured = {}

    def fake_build_structured_input(payload, fhir_patient_id, document_patient_id, docs_prefix):
        captured["fhir_patient_id"] = fhir_patient_id
        captured["document_patient_id"] = document_patient_id
        captured["docs_prefix"] = docs_prefix
        return ("structured", {"context_sent_to_llm": {}})

    monkeypatch.setattr(orch, "_build_structured_input", fake_build_structured_input)

    class StubRunner:
        def run(self, user_id, session_id, new_message):
            event = type("E", (), {})()
            event.content = types.Content(role="model", parts=[types.Part(text='{"answer":"ok","literacy_level":"medium","empathy_level":"medium"}')])
            yield event

    monkeypatch.setattr(orch, "_runner", StubRunner())

    out = orch.run_chat(orch.ChatInput(user_id="test_user", message="What do my notes say about nausea?"))
    assert out.answer == "ok"
    assert captured["fhir_patient_id"] == "fhir-123"
    assert captured["document_patient_id"] == "emily-wilson"
    assert captured["docs_prefix"] == "patients/emily-wilson/"
