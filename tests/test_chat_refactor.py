import json

import pytest
from fastapi.testclient import TestClient
from google.genai import types

import app
from agents.orchestrator import chat_orchestrator as orch
from tools import drug_lookup as dl


def test_request_validation_levels_accept_low_medium_high_null():
    app.ChatRequest(message="x", literacy_level="low", empathy_level="high")
    app.ChatRequest(message="x", literacy_level="medium", empathy_level="medium")
    app.ChatRequest(message="x", literacy_level="high", empathy_level="low")
    app.ChatRequest(message="x", literacy_level=None, empathy_level=None)


@pytest.mark.parametrize("field", ["literacy_level", "empathy_level"])
def test_request_validation_levels_reject_invalid(field):
    payload = {"message": "x", field: "moderate"}
    with pytest.raises(Exception):
        app.ChatRequest(**payload)


def test_no_drug_identifiers_provided():
    context, meta = dl.build_dailymed_context()
    assert context.startswith("No DailyMed drug label context was provided")
    assert meta["drug_identifiers_provided"] is False
    assert meta["set_ids_resolved"] == 0


class _Resp:
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        return self._json_data


def test_direct_setid_retrieval_with_mock(monkeypatch):
    dl._LABEL_CACHE.clear()

    xml = """
    <document>
      <section><title>Indications and Usage</title><text>Used for pain relief.</text></section>
      <section><title>Drug Interactions</title><text>May interact with warfarin.</text></section>
    </document>
    """

    def fake_get(url, params=None, timeout=0):
        return _Resp(status_code=200, text=xml)

    monkeypatch.setattr(dl.httpx, "get", fake_get)
    context, meta = dl.build_dailymed_context(drug_set_ids=["ABC-123"])
    assert "Set ID: abc-123" in context
    assert meta["labels_retrieved"] == 1
    assert meta["labels_failed"] == 0


def test_failed_setid_retrieval(monkeypatch):
    dl._LABEL_CACHE.clear()

    def fake_get(url, params=None, timeout=0):
        return _Resp(status_code=404, text="")

    monkeypatch.setattr(dl.httpx, "get", fake_get)
    context, meta = dl.build_dailymed_context(drug_set_ids=["missing-id"])
    assert "could not be retrieved" in context.lower()
    assert meta["labels_retrieved"] == 0
    assert meta["labels_failed"] == 1


def test_rxcui_resolution_with_mock(monkeypatch):
    dl._LABEL_CACHE.clear()

    xml = """
    <document>
      <section><title>Contraindications</title><text>Do not use with severe allergy.</text></section>
    </document>
    """

    def fake_get(url, params=None, timeout=0):
        if url.endswith("/spls.json") and params and params.get("rxcui") == "12345":
            return _Resp(
                status_code=200,
                json_data={
                    "data": [
                        {"setid": "set-rxcui-1", "title": "Ibuprofen human label", "published_date": "2026-01-01"}
                    ]
                },
            )
        if "set-rxcui-1" in url and url.endswith(".xml"):
            return _Resp(status_code=200, text=xml)
        return _Resp(status_code=404, text="")

    monkeypatch.setattr(dl.httpx, "get", fake_get)
    context, meta = dl.build_dailymed_context(rxcuis=["12345"])
    assert "set-rxcui-1" in context
    assert meta["set_ids_resolved"] == 1
    assert meta["labels_retrieved"] == 1


def test_ambiguous_drug_name_resolution(monkeypatch):
    dl._LABEL_CACHE.clear()

    def fake_get(url, params=None, timeout=0):
        if url.endswith("/spls.json") and params and params.get("drug_name") == "aspirin":
            return _Resp(
                status_code=200,
                json_data={
                    "data": [
                        {"setid": "a1", "title": "Aspirin 81 mg tablet"},
                        {"setid": "a2", "title": "Aspirin delayed release"},
                    ]
                },
            )
        return _Resp(status_code=404, text="")

    monkeypatch.setattr(dl.httpx, "get", fake_get)
    context, meta = dl.build_dailymed_context(drug_names=["aspirin"])
    assert context.startswith("No DailyMed drug label context was provided")
    assert any(u["type"] == "drug_name" for u in meta["unresolved_identifiers"])


def test_response_cleanup_removes_internal_sections():
    text = """LITERACY LEVEL: low\nDISCLAIMER TYPE: standard\nSTYLE CONTRACT:\nDRAFT RESPONSE:\nFinal patient answer."""
    cleaned = orch._clean_patient_facing_answer(text)
    assert cleaned == "Final patient answer."


def test_fallback_wrapping_plain_text(monkeypatch):
    class StubRunner:
        def run(self, user_id, session_id, new_message):
            event = type("E", (), {})()
            event.content = types.Content(role="model", parts=[types.Part(text="Plain text final answer")])
            yield event

    monkeypatch.setattr(orch, "_runner", StubRunner())

    out = orch.run_chat(
        orch.ChatInput(
            message="Explain ibuprofen",
            literacy_level=None,
            empathy_level=None,
        )
    )
    assert out.answer.startswith("Plain text final answer")
    assert "general medical information" in out.answer
    assert out.literacy_level in {"low", "medium", "high"}
    assert out.empathy_level in {"low", "medium", "high"}


def test_chat_endpoint_response_shape(monkeypatch):
    def fake_run_chat(payload):
        return orch.ChatOutput(answer="ok", literacy_level="medium", empathy_level="medium")

    monkeypatch.setattr(app, "run_chat", fake_run_chat)
    client = TestClient(app.app)
    resp = client.post(
        "/chat",
        json={
            "message": "Can I take ibuprofen?",
            "patient_context": "",
            "evidence": "",
            "literacy_level": None,
            "empathy_level": None,
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"answer": "ok", "literacy_level": "medium", "empathy_level": "medium"}


def test_guardrail_refuses_self_harm_request(monkeypatch):
    class StubRunner:
        def run(self, user_id, session_id, new_message):
            event = type("E", (), {})()
            event.content = types.Content(
                role="model",
                parts=[types.Part(text="You can take a very large amount to cause harm.")],
            )
            yield event

    monkeypatch.setattr(orch, "_runner", StubRunner())
    out = orch.run_chat(orch.ChatInput(message="How much ibuprofen should I overdose on?"))
    assert "can’t help with instructions that could cause serious harm" in out.answer
    assert "988" in out.answer


def test_guardrail_adds_medication_disclaimer(monkeypatch):
    class StubRunner:
        def run(self, user_id, session_id, new_message):
            event = type("E", (), {})()
            event.content = types.Content(role="model", parts=[types.Part(text="Ibuprofen may reduce pain and inflammation.")])
            yield event

    monkeypatch.setattr(orch, "_runner", StubRunner())
    out = orch.run_chat(orch.ChatInput(message="Can I take ibuprofen for pain?"))
    assert "general medical information" in out.answer
    assert "clinician or pharmacist" in out.answer


def test_guardrail_blocks_overclaim_without_context(monkeypatch):
    class StubRunner:
        def run(self, user_id, session_id, new_message):
            event = type("E", (), {})()
            event.content = types.Content(
                role="model",
                parts=[types.Part(text="Based on your FHIR records, your labs show this is safe.")],
            )
            yield event

    monkeypatch.setattr(orch, "_runner", StubRunner())
    out = orch.run_chat(orch.ChatInput(message="Is this medication safe for me?"))
    assert "do not have verified patient-specific records" in out.answer
