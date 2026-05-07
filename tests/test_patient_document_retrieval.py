from tools.patient_document_retrieval import build_patient_document_context
from tools.patient_document_selector import select_patient_document_needs


def test_document_selector_medication_question():
    out = select_patient_document_needs("Can I take ibuprofen with warfarin?", intent="medication_safety")
    assert out["needed_document_types"] == ["medication_management", "oncology_notes", "care_coordination"]


def test_document_selector_lab_question():
    out = select_patient_document_needs("What does my WBC mean?", intent="lab_interpretation")
    assert out["needed_document_types"] == ["oncology_notes"]


def test_document_selector_general_education():
    out = select_patient_document_needs("What is ibuprofen?", intent="general_education")
    assert out["needed_document_types"] == []
    assert out["query_terms"] == []


def test_retrieval_no_document_types_selected():
    out = build_patient_document_context({"needed_document_types": [], "query_terms": []})
    assert out == "No patient-specific unstructured document context was selected for this request."


def test_retrieval_ignores_keep_files(monkeypatch):
    from tools import patient_document_retrieval as pdr

    class Blob:
        def __init__(self, name, text):
            self.name = name
            self._text = text

        def download_as_text(self):
            return self._text

    class Client:
        def list_blobs(self, bucket, prefix):
            return [
                Blob("patients/emily-wilson/medication_management/.keep", "ibuprofen mention"),
                Blob(
                    "patients/emily-wilson/medication_management/meds.md",
                    "ibuprofen side effects and pharmacy follow-up",
                ),
            ]

    monkeypatch.setattr(pdr.storage, "Client", lambda: Client())

    out = build_patient_document_context(
        {
            "needed_document_types": ["medication_management"],
            "query_terms": ["ibuprofen", "pharmacy"],
        }
    )
    assert ".keep" not in out
    assert "meds.md" in out


def test_retrieval_limits_context_length(monkeypatch):
    from tools import patient_document_retrieval as pdr

    long_chunk = "ibuprofen " * 3000

    class Blob:
        def __init__(self, name, text):
            self.name = name
            self._text = text

        def download_as_text(self):
            return self._text

    class Client:
        def list_blobs(self, bucket, prefix):
            return [
                Blob("patients/emily-wilson/oncology_notes/note1.md", long_chunk),
                Blob("patients/emily-wilson/oncology_notes/note2.md", long_chunk),
                Blob("patients/emily-wilson/oncology_notes/note3.md", long_chunk),
            ]

    monkeypatch.setattr(pdr.storage, "Client", lambda: Client())

    out = build_patient_document_context(
        {
            "needed_document_types": ["oncology_notes"],
            "query_terms": ["ibuprofen"],
        }
    )
    assert len(out) <= 5600
    assert "[truncated to context limit]" in out
