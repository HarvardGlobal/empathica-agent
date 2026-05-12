from google.genai import types

from agents.orchestrator import chat_orchestrator as orch
from tools.fhir_patient_context import build_fhir_patient_context
from tools.patient_context_selector import select_patient_context_needs


def test_selector_medication_safety_intent():
    r = select_patient_context_needs("Can I take ibuprofen with warfarin?")
    assert r["intent"] == "medication_safety"
    assert "allergies" in r["needed_context_categories"]


def test_selector_allergy_message_includes_allergies():
    r = select_patient_context_needs("Can I take this if I am allergic to aspirin?")
    assert r["intent"] in {"allergy_check", "medication_safety"}
    assert "allergies" in r["needed_context_categories"]


def test_selector_lab_interpretation_intent():
    r = select_patient_context_needs("What does my eGFR mean?")
    assert r["intent"] == "lab_interpretation"
    assert "Observation" in r["needed_fhir_resources"]


def test_selector_general_education_intent():
    r = select_patient_context_needs("What is ibuprofen?")
    assert r["intent"] == "general_education"
    assert r["needed_fhir_resources"] == []


def test_fhir_context_missing_note():
    out = build_fhir_patient_context(
        {
            "intent": "general_education",
            "needed_context_categories": [],
            "needed_fhir_resources": [],
            "reason": "",
        }
    )
    assert out == "No patient specific FHIR context was selected for this request."


def test_fhir_context_builder_summarizes_mocked_resources(monkeypatch):
    from tools import fhir_patient_context as fpc

    def fake_get(path, params=None):
        if path.startswith("Patient/"):
            return {
                "id": "72658ba3-2eea-4889-bd66-8df7f667657e",
                "name": [{"given": ["Emily"], "family": "Wilson"}],
                "gender": "female",
                "birthDate": "1963-01-01",
            }
        if path == "MedicationStatement":
            return {
                "entry": [
                    {"resource": {"medicationCodeableConcept": {"text": "Warfarin 5 mg"}}},
                ]
            }
        if path == "AllergyIntolerance":
            return {
                "entry": [
                    {"resource": {"code": {"text": "Aspirin allergy"}}},
                ]
            }
        if path == "Condition":
            return {
                "entry": [
                    {"resource": {"code": {"text": "Atrial fibrillation"}}},
                ]
            }
        if path == "Observation":
            return {
                "entry": [
                    {
                        "resource": {
                            "code": {"text": "eGFR"},
                            "valueQuantity": {"value": 62, "unit": "mL/min/1.73m2"},
                            "effectiveDateTime": "2026-05-01",
                        }
                    }
                ]
            }
        return None

    monkeypatch.setattr(fpc, "_fhir_get_json", fake_get)
    out = build_fhir_patient_context(
        {
            "intent": "medication_safety",
            "needed_context_categories": ["active_medications", "allergies", "active_conditions", "relevant_labs"],
            "needed_fhir_resources": ["Patient", "MedicationStatement", "AllergyIntolerance", "Condition", "Observation"],
            "reason": "",
        }
    )
    assert "FHIR PATIENT CONTEXT USED:" in out
    assert "Emily Wilson" in out
    assert "Warfarin 5 mg" in out
    assert "Aspirin allergy" in out
    assert "Atrial fibrillation" in out
    assert "eGFR" in out


def test_orchestrator_prompt_includes_selection_and_missing_note(monkeypatch):
    captured = {"prompt": ""}

    class StubRunner:
        def run(self, user_id, session_id, new_message):
            captured["prompt"] = new_message.parts[0].text
            event = type("E", (), {})()
            event.content = types.Content(
                role="model",
                parts=[
                    types.Part(
                        text='{"answer":"ok","literacy_level":"medium","empathy_level":"medium"}'
                    )
                ],
            )
            yield event

    monkeypatch.setattr(orch, "_runner", StubRunner())

    out = orch.run_chat(
        orch.ChatInput(
            message="Can I take ibuprofen with warfarin?",
            patient_context=None,
            evidence=None,
            drug_set_ids=None,
            literacy_level=None,
            empathy_level=None,
        )
    )
    assert out.answer.startswith("ok")
    assert "general medical information" in out.answer
    assert "PATIENT CONTEXT SELECTION" in captured["prompt"]
    assert "FHIR PATIENT CONTEXT" in captured["prompt"]
    assert "USER PROVIDED SUPPLEMENTARY PATIENT CONTEXT" in captured["prompt"]
