# Empathica — Medication Reasoning Chatbot

An ADK multi-agent chatbot that answers patient medication questions with clinically grounded answers adapted to the patient's health literacy level.

---

## Architecture

```
User question
  → empathica_orchestrator  (root agent)
      ├── make_literacy_decision_tool   classify literacy level + detect overrides
      ├── drug_lookup                   retrieve drug facts (stub → wire real backend)
      ├── get_patient_context           retrieve patient medications/conditions (stub)
      ├── check_allergies               verify allergy conflicts (stub)
      └── retrieve_literature           semantic literature search (stub)
  → medically grounded draft
  → literacy_adaptation  (sub-agent)
  → final patient-facing answer
```

### Root agent: `empathica_orchestrator`

Defined in [agents/orchestrator/agent.py](agents/orchestrator/agent.py).

Responsibilities:
1. Classify the patient's health literacy level on every turn.
2. Detect safety emergencies and clinical-judgment requests (override handling).
3. Call only the tools needed for the specific question.
4. Produce a clinically accurate draft — never fabricate drug or patient data.
5. Delegate the draft to `literacy_adaptation` for final communication.

### Literacy adaptation agent: `literacy_adaptation`

Defined in [agents/literacy_assessor/agent.py](agents/literacy_assessor/agent.py).

This agent is a **controlled final-response layer**, not a medical decision maker.

Responsibilities:
- Rewrite the orchestrator's draft for the detected literacy level (low / moderate / high).
- Preserve all clinical facts, warnings, contraindications, and uncertainty.
- Adjust vocabulary, sentence length, structure, and tone.
- Include the correct literacy-appropriate disclaimer.
- Never add new medical facts or remove safety information.

### How they are connected

`literacy_adaptation` is wired as a `sub_agent` of `empathica_orchestrator` in [agents/orchestrator/agent.py](agents/orchestrator/agent.py). The orchestrator delegates to it using ADK's transfer mechanism after producing the clinical draft. The literacy agent is never exposed as a standalone deployment target.

---

## Running locally

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in environment variables
cp .env.example .env
# Edit .env — at minimum set GOOGLE_CLOUD_PROJECT or GOOGLE_API_KEY

# 3. Run with ADK
adk run .

# 4. Or open the ADK web UI
adk web .
```

---

## Deploying to Vertex AI

```bash
# Authenticate
gcloud auth application-default login

# Deploy — ADK loads root_agent from agent.py
adk deploy . \
  --project $GOOGLE_CLOUD_PROJECT \
  --region $GOOGLE_CLOUD_LOCATION \
  --staging-bucket $STAGING_BUCKET
```

The deployed entrypoint is `empathica_orchestrator`. ADK locates it via `root_agent` in [agent.py](agent.py).

---

## Running tests

```bash
# All tests
pytest

# Smoke / import tests only (no LLM calls)
pytest tests/test_imports.py -v

# Literacy scorer unit tests
pytest tests/test_literacy_scorer.py -v
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Yes (Vertex) | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | Yes (Vertex) | Deployment region (e.g. `us-central1`) |
| `GOOGLE_GENAI_USE_VERTEXAI` | Yes (Vertex) | Set `true` to use Vertex AI auth |
| `STAGING_BUCKET` | Deploy only | GCS bucket for `adk deploy` |
| `GOOGLE_API_KEY` | Local dev | API key auth (instead of Vertex AI) |
| `GEMINI_MODEL` | No | Model override (default: `gemini-2.0-flash`) |
| `DRUG_KNOWLEDGE_API_URL` | No | Drug knowledge service URL (stubs if empty) |
| `PATIENT_CONTEXT_API_URL` | No | Patient context / EHR service URL |
| `LITERATURE_RETRIEVAL_API_URL` | No | RAG / literature retrieval service URL |
| `DEFAULT_LITERACY_LEVEL` | No | Fallback literacy level (default: `moderate`) |

See [.env.example](.env.example) for the full reference.

---

## Secret Manager

For production, supply the following via Google Secret Manager rather than environment variables:

- `GOOGLE_API_KEY` — if using API key auth
- Any service credentials for `DRUG_KNOWLEDGE_API_URL`, `PATIENT_CONTEXT_API_URL`, `LITERATURE_RETRIEVAL_API_URL`

Reference secrets in your Vertex AI deployment config using the `secretEnv` field. Never commit credentials to source control.

---

## Wiring real backends

The four tools in [tools/](tools/) return structured stub responses when their backend URLs are not set. To connect a real service:

1. Set the relevant URL in `.env` (e.g. `DRUG_KNOWLEDGE_API_URL=https://...`).
2. The tool will call that URL automatically — no code change needed for standard REST responses.
3. For non-standard APIs, replace the `httpx` call in the tool module with your client code.

---

## Literacy levels

| Level | Audience | Style |
|---|---|---|
| Low | Grade 4–6 | Plain words, short sentences, bullets, no jargon |
| Moderate | Grade 7–9 | Basic terms explained, practical headings *(default)* |
| High | Grade 10+ | Technical terminology, mechanistic detail, clinical structure |

Literacy level controls **communication style only** — it never affects clinical content.
