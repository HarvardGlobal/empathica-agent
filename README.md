# Empathica — Medication Reasoning Chatbot

Cloud Run + FastAPI service that runs an ADK orchestrator for medication guidance with:
- literacy/empathy adaptation
- DailyMed label context
- optional FHIR patient context selection
- optional patient-specific document snippets from GCS

## Current Architecture

`POST /chat` in `app.py`
→ `agents/orchestrator/chat_orchestrator.py`
→ ADK `Runner` using `root_agent` from `agent.py`
→ orchestrator agent + literacy sub-agent
→ API returns strict JSON response

Detailed architecture reference:
- `docs/architecture-overview.md`
- `docs/architecture-final.svg`

### Main runtime files
- `app.py`: HTTP API wrapper (`/chat`, `/healthz`)
- `agent.py`: ADK root export (`root_agent`)
- `agents/orchestrator/agent.py`: orchestrator ADK agent definition
- `agents/orchestrator/chat_orchestrator.py`: structured input assembly, ADK run, output parsing/cleanup

### Context/tool files used by `/chat`
- `tools/drug_lookup.py`: DailyMed resolution + label extraction
- `tools/patient_context_selector.py`: deterministic patient-context intent selection
- `tools/fhir_patient_context.py`: selected FHIR resource retrieval/summarization
- `tools/patient_document_selector.py`: deterministic unstructured-doc selection
- `tools/patient_document_retrieval.py`: GCS snippet retrieval/ranking
- `tools/literature_retrieval.py`: evidence context block
- `tools/allergy_check.py`: allergy context block

## API Contract

### `POST /chat`

Request:
```json
{
  "user_id": "000-001",
  "message": "Can I take ibuprofen for knee pain?",
  "patient_context": "optional string",
  "evidence": "optional string",
  "drug_set_ids": ["optional set id"],
  "literacy_level": null,
  "empathy_level": null
}
```

Response (exact shape):
```json
{
  "answer": "...",
  "literacy_level": "low | medium | high",
  "empathy_level": "low | medium | high"
}
```

### `POST /onboarding/upload`

Multipart endpoint to onboard one user with:
- `structured_fhir_file` (JSON FHIR Patient or Bundle containing Patient with id)
- `unstructured_file` (any unstructured document blob)
- `user_id` (deterministic application identity)
- `target_document_types` (optional comma-separated folder hints, e.g. `medication_management,oncology_notes`)

This endpoint:
1. Imports FHIR payload into configured FHIR store.
2. Uploads unstructured file to `gs://$PATIENT_DOCS_BUCKET/patients/<fhir_patient_id>/uploads/...`.
3. Materializes typed markdown summaries into patient folders (for example `medication_management`, `oncology_notes`, `care_coordination`, with fallback `general_notes`).
4. Upserts Firestore identity mapping in `IDENTITY_MAP_COLLECTION`.

Optional doc type customization:
- `PATIENT_DOC_TYPE_KEYWORDS_JSON` (env var): JSON object mapping `doc_type -> keyword list` used for automatic section classification.

## Model Configuration

Runtime model config is environment-driven:
- `GOOGLE_GENAI_MODEL` (default: `gemini-2.5-flash`)
- `GOOGLE_CLOUD_LOCATION` (Vertex location, expected `us-central1`)

Cloud Run deploy remains in `us-east4`; Vertex model location remains `us-central1`.

## Deploy (Cloud Run via Cloud Build)

Key files:
- `Dockerfile`
- `cloudbuild.yaml`

`cloudbuild.yaml` builds/pushes image and deploys Cloud Run service `empathica-agents`.

Deployment runbook:
- `docs/deployment-google-cloud.md`
- `docs/private-cloud-run-auth-setup.md` (private access + backend auth flow)

## Branching and PR Governance

- `main` is production and must be merged by pull request only.
- Any PR to `main` requires explicit approval from the repository owner.
- `develop` is the integration branch for validated changes.
- Feature and fix work should be done from short-lived branches and merged by PR.

Reference:
- `docs/branching-and-pr-policy.md`
- `docs/release-checklist.md`

## Security Expectations

- Use Secret Manager for sensitive values.
- Keep Cloud Run private unless explicit public access is required.
- Limit runtime and CI IAM permissions to least privilege.
- Avoid logging patient-sensitive content.

Reference:
- `docs/security-baseline.md`

## Environment Variables

Core runtime:
- `GOOGLE_GENAI_USE_VERTEXAI=true`
- `GOOGLE_CLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION=us-central1`
- `GOOGLE_GENAI_MODEL=gemini-2.5-flash`

FHIR context:
- `FHIR_PROJECT_ID`
- `FHIR_LOCATION`
- `FHIR_DATASET`
- `FHIR_STORE`

Patient documents (GCS):
- `PATIENT_DOCS_BUCKET`

Identity mapping (Firestore):
- `IDENTITY_MAP_COLLECTION` (default: `patient_identity_map`)

## Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

## Tests

```bash
pytest -q
```

## Notes

- `agents/orchestrator/agent.py` still contains ADK tool-call interfaces for legacy compatibility/testing.
- `chat_orchestrator.py` is the active API path for structured context orchestration.
