# EMPATHICA Backend

EMPATHICA is a patient-centred medication reasoning backend built as a FastAPI service on Google Cloud Run. It uses Google ADK to orchestrate a small agent chain, Gemini for answer generation, FHIR for structured patient data, Firestore-backed semantic document RAG for unstructured patient notes, and DailyMed for official drug label evidence.

The goal of the system is not to invent medical answers from scratch. It assembles the relevant evidence, reasons from that evidence, then returns a cautious patient-facing response with literacy and empathy adaptation.

## Project Overview

This implementation includes:

- a `POST /chat` API endpoint served by Cloud Run
- a deterministic identity map that separates `user_id`, `fhir_patient_id`, and `document_patient_id`
- structured retrieval from FHIR patient records
- unstructured retrieval from patient documents via Firestore-based semantic RAG
- DailyMed label lookup for drug-specific evidence
- literacy and empathy adaptation
- safety-first response formatting
- Cloud Build and Cloud Run deployment

The backend is designed to work for all users and all patients, not just one demo patient.

## Authentication and Access

The Cloud Run service is deployed without unauthenticated access.

- callers must have Cloud Run Invoker permission, or use an allowed service account
- requests to `/chat` need a Google identity token in the `Authorization` header
- this keeps the backend from being publicly callable
- a browser frontend should normally call its own backend, or use an approved auth flow, rather than handling privileged service credentials directly

## High-Level Architecture

```text
Client
→ authenticated backend/API layer
→ private Cloud Run /chat service
→ Chat orchestrator
→ identity resolution
→ retrieval planning
→ FHIR retrieval
→ document RAG retrieval
→ DailyMed retrieval
→ answer generation
→ literacy and empathy adaptation
→ safety and response formatting
→ JSON response
```

### Main layers

| Layer | Responsibility |
|---|---|
| Client | Calls an authenticated backend layer or a private Cloud Run `/chat` service. |
| Authenticated backend/API layer | Exposes `/chat`, `/healthz`, and onboarding upload routes through FastAPI when Cloud Run IAM allows access. |
| Chat orchestrator | Resolves identity, plans retrieval, executes context fetches, and assembles the structured prompt for the agent chain. |
| Agent layer | ADK agents perform the final answer drafting and guardrail checks. |
| Retrieval layer | Fetches FHIR context, document RAG snippets, and DailyMed evidence. |
| Data sources | FHIR store, GCS patient documents, Firestore RAG database, DailyMed service. |
| Evidence summary and response shaping | Produces concise `evidence_summary`, `context_sources`, and optional `debug`. |
| Cloud deployment layer | Docker, Cloud Build, Artifact Registry, and Cloud Run. |

## Main Agents

The code splits responsibilities across three ADK agents.

### 1. Root orchestration agent

Actual code:

- `src/agents/orchestrator/agent.py`
- `src/agents/orchestrator/chat_orchestrator.py`

Responsibilities:

- receives the request and message metadata
- resolves patient identity
- decides what context is needed
- coordinates FHIR, document RAG, and DailyMed retrieval
- builds the combined evidence package
- passes the evidence to the answer writer
- does not invent patient facts

This agent is the control plane. It decides what to fetch and what to pass downstream, but it does not fabricate clinical content.

### 2. Medical answer generation / reasoning agent

Actual code:

- `src/agents/answer_writer/agent.py`
- prompt: `src/system_prompts/active/answer_writer_medical_reasoning_v1.txt`

Responsibilities:

- uses only retrieved and provided context
- produces the medical education answer
- grounds the response in available evidence
- handles missing context cautiously
- avoids unsupported claims
- preserves medical safety wording

This is the layer that turns evidence into a patient-facing answer.

### 3. Response guardrail agent

Actual code:

- `src/agents/response_guardrail/agent.py`

Responsibilities:

- checks the draft answer
- enforces safety wording and output constraints
- rejects or minimally repairs unsafe output
- returns the final response

This is the terminal safety layer.

### Literacy and empathy adaptation

The repository also contains literacy and empathy control logic in the orchestrator layer. The behavior is:

- adjust readability and tone
- keep the clinical meaning unchanged
- do not add new medical facts
- do not remove safety warnings
- keep escalation guidance intact
- support low, medium, and high literacy outputs

The final user-facing answer should be readable, but it must remain clinically grounded.

## Identity Resolution

`user_id` is the application identity used by the frontend or caller. It is not automatically the same as the FHIR patient ID or the document RAG patient ID.

Identity mapping is handled by:

- `src/tools/patient/identity_map.py`

Identity records include:

- `user_id`
- `tenant`
- `fhir_patient_id`
- `document_patient_id`
- `docs_prefix`
- `status`

### How the IDs are used

- **FHIR retrieval** uses `fhir_patient_id`
- **Document RAG** uses `document_patient_id`
- **`docs_prefix`** points to the patient folder in the GCS document bucket
- `document_patient_id` may be stored explicitly or derived from `docs_prefix`
- if no document-specific identity exists, the system falls back to `fhir_patient_id`

### General identity flow

```text
user_id
→ identity map lookup
→ fhir_patient_id for structured FHIR retrieval
→ document_patient_id + docs_prefix for document RAG
```

This separation is what keeps FHIR retrieval and document retrieval isolated even when the FHIR patient ID and document patient folder are different.

## Data Sources

### A. FHIR structured patient data

FHIR retrieval is used for structured clinical context such as:

- demographics
- active medications
- allergies
- active conditions
- kidney function
- liver function
- blood counts
- cardiovascular context
- bleeding risk context
- GI risk context
- vital signs

The system uses domain-based retrieval rather than passing every FHIR resource into the model. That keeps prompts smaller, reduces noise, and avoids overfetching.

Missing domains are represented explicitly in the retrieval package instead of being silently ignored.

Relevant code:

- `src/tools/patient/fhir_patient_context.py`
- `src/tools/patient/patient_context_selector.py`
- `src/agents/orchestrator/context_catalog.py`
- `src/agents/orchestrator/fhir_context_executor.py`

### B. Firestore-based document RAG

Unstructured patient documents are stored in GCS, then indexed into Firestore for retrieval.

Indexing and runtime retrieval use:

- `src/tools/documents/index_all_patient_documents.py`
- `src/tools/documents/document_ingestion.py`
- `src/tools/documents/document_chunker.py`
- `src/tools/documents/document_embedding.py`
- `src/tools/documents/document_rag_store.py`
- `src/tools/documents/patient_document_rag.py`

How it works:

1. GCS stores the source documents.
2. Cloud Build runs the indexer.
3. Documents are chunked and embedded.
4. Metadata and embeddings are stored in Firestore.
5. Runtime retrieval filters chunks by `patient_id`.
6. Only chunks for the resolved `document_patient_id` are considered.
7. The answer layer receives concise snippets and document metadata.

The key isolation rule is simple:

> The document RAG `patient_id` must match the `patient_id` stored on the indexed chunks.

This backend uses Firestore-backed semantic RAG rather than Vertex AI Vector Search because it is lighter weight and more cost conscious for the current deployment.

### C. DailyMed drug label evidence

DailyMed provides official drug label evidence.

The system uses it when the question needs medication-specific label information such as:

- interactions
- warnings
- contraindications
- adverse reactions
- dosage or administration context

Important behavior:

- explicit drug targets should be looked up directly
- unnecessary lookup of supplements, foods, teas, and supportive items should be avoided unless they are the actual question target
- name-based matching can resolve to a product label that may not be the exact patient product or formulation
- evidence summaries should make that match note explicit

Relevant code:

- `src/tools/medications/drug_lookup.py`
- `src/agents/orchestrator/dailymed_context_executor.py`
- `src/agents/orchestrator/unified_medication_evidence_package.py`

### D. User supplied context

The API supports optional user-supplied context through `patient_context`.

This is not the same as retrieved context:

- retrieved context comes from FHIR, document RAG, and DailyMed
- user supplied context comes directly from the request payload

The orchestrator includes it in the structured prompt, but it is still treated as user-supplied input rather than verified clinical evidence.

## Retrieval Planning

The orchestrator first classifies the request intent, then decides what context is needed.

This matters because different question types need different evidence:

- medication safety questions may need medications, allergies, conditions, labs, document notes, and drug labels
- general education questions may need little or no patient-specific context
- current medication list questions should retrieve active medications, but not necessarily DailyMed labels
- document-related questions should trigger document RAG when the user references notes, uploads, care plans, clinician notes, or similar language

Missing context is explicit. The system prefers to say that a source was unavailable rather than silently pretending it exists.

Relevant code:

- `src/agents/orchestrator/orchestrator_context_planner.py`
- `src/agents/orchestrator/retrieval_plan_validator.py`
- `src/agents/orchestrator/fhir_context_executor.py`
- `src/agents/orchestrator/chat_orchestrator.py`

## Medication Safety Flow

Medication safety questions generally flow like this:

1. detect explicit drug mentions
2. retrieve the current medication list from FHIR when needed
3. retrieve allergies, active conditions, and relevant observations when needed
4. retrieve DailyMed label evidence for explicit drug targets when needed
5. retrieve document RAG snippets when the question references patient notes or uploads
6. combine the evidence into a unified package
7. generate a cautious patient-friendly answer
8. include clinician or pharmacist confirmation guidance when appropriate

This flow is designed to work for general medication questions, not just any one example drug.

Relevant code:

- `src/agents/orchestrator/medication_planner.py`
- `src/agents/orchestrator/medication_plan_validator.py`
- `src/agents/orchestrator/fhir_medication_executor.py`
- `src/agents/orchestrator/dailymed_context_executor.py`
- `src/agents/orchestrator/unified_medication_evidence_package.py`

## Document RAG Flow

### Indexing time

1. Read documents from GCS.
2. Ignore placeholder files.
3. Extract the document patient ID from the folder path.
4. Chunk the documents.
5. Generate embeddings.
6. Store document records and chunk records in Firestore.
7. Track indexing runs.

### Runtime

1. Resolve user identity.
2. Determine `document_patient_id`.
3. Embed or process the query.
4. Filter candidate chunks by `patient_id`.
5. Retrieve the top relevant chunks.
6. Return snippets, document types, source files, and retrieval metadata.
7. Pass concise document context to answer generation.

Relevant code:

- `src/tools/documents/index_all_patient_documents.py`
- `src/tools/documents/document_ingestion.py`
- `src/tools/documents/document_chunker.py`
- `src/tools/documents/document_embedding.py`
- `src/tools/documents/document_rag_store.py`
- `src/tools/documents/patient_document_rag.py`

## Response Format

The normal `/chat` response is a compact JSON object.

Typical fields:

- `answer`
- `literacy_level`
- `empathy_level`
- `evidence_summary`
- `context_sources`
- `debug`

### Meaning of the fields

- `answer`: the final patient-facing answer
- `literacy_level`: resolved literacy output level
- `empathy_level`: resolved empathy output level
- `evidence_summary`: compact summary of which sources were used
- `context_sources`: short list of source types and summaries
- `debug`: full internal trace, returned only when explicitly requested or enabled by environment

By default, the response suppresses the full debug payload.

Relevant code:

- `src/app.py`
- `src/agents/orchestrator/chat_orchestrator.py`

## Safety and Grounding Rules

The system follows these rules:

- base answers on retrieved context and user-supplied context
- do not invent patient facts
- acknowledge missing information
- recommend clinician or pharmacist confirmation for medication decisions
- escalate urgent symptoms
- keep literacy adaptation from changing clinical meaning
- do not remove safety warnings

The answer writer prompt enforces this directly:

- `src/system_prompts/active/answer_writer_medical_reasoning_v1.txt`

## Environment Variables and Cloud Services

| Variable | Purpose |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | Default Google Cloud project for runtime services. |
| `GOOGLE_CLOUD_LOCATION` | Cloud Run / Vertex location. |
| `GOOGLE_GENAI_USE_VERTEXAI` | Tells the Gemini client to use Vertex AI instead of a direct API path. |
| `GOOGLE_GENAI_MODEL` | Gemini model name used by the agent runtime. |
| `FHIR_PROJECT_ID` | Google Cloud project that hosts the FHIR store. |
| `FHIR_LOCATION` | Location of the FHIR dataset/store. |
| `FHIR_DATASET` | FHIR dataset name. |
| `FHIR_STORE` | FHIR store name. |
| `PATIENT_DOCS_BUCKET` | GCS bucket that stores patient document source files. |
| `PATIENT_DOCS_PREFIX` | Root prefix inside the bucket for patient document folders. |
| `FIRESTORE_IDENTITY_DATABASE_ID` | Firestore database used for identity mapping. |
| `FIRESTORE_DATABASE_ID` | General Firestore database override used by some deployment paths. |
| `IDENTITY_MAP_COLLECTION` | Firestore collection name for user-to-patient identity records. |
| `FIRESTORE_DOCUMENT_RAG_DATABASE_ID` | Firestore database that stores document RAG documents and chunks. |
| `FIRESTORE_DOCUMENT_COLLECTION` | Firestore collection for document-level RAG records. |
| `FIRESTORE_CHUNK_COLLECTION` | Firestore collection for chunk-level RAG records. |
| `FIRESTORE_INDEXING_RUNS_COLLECTION` | Firestore collection for indexing run metadata. |
| `DOCUMENT_RAG_ENABLED` | Enables or disables document RAG at runtime. |
| `DOCUMENT_RAG_BACKEND` | Selects the document RAG backend implementation. |
| `VERTEX_AI_PROJECT` | Project used when initializing the Vertex embedding client. |
| `VERTEX_AI_REGION` | Vertex region used for embedding model initialization. |
| `EMBEDDING_MODEL_NAME` | Embedding model used during document indexing and retrieval. |
| `ALLOW_FAKE_EMBEDDINGS` | Allows fallback embeddings only for non-production development. |
| `KEYWORD_FALLBACK_ENABLED` | Enables keyword fallback when semantic document retrieval fails. |

Additional environment variables may exist in deployment scripts and Cloud Build configuration, but the variables above are the ones used directly by the backend code.

## Deployment and Build Flow

The deployment path is:

1. Build a Docker image.
2. Push the image to Artifact Registry.
3. Run document RAG tests in Cloud Build.
4. Run the document indexing step.
5. Deploy to Cloud Run.
6. Run the service under a dedicated Cloud Run service account.
7. Keep Cloud Run private unless explicit public access is intended.

Relevant files:

- `Dockerfile`
- `cloudbuild.yaml`
- `ops/deploy_vertex.sh`
- `ops/cloud_run_client.py`
- `documentation/deployment-google-cloud.md`
- `documentation/private-cloud-run-auth-setup.md`

### Private Cloud Run invocation

When Cloud Run is private, the caller must include an identity token. A typical pattern is:

```bash
SERVICE_URL=$(gcloud run services describe empathica-agents \
  --region us-east4 \
  --format='value(status.url)')

TOKEN=$(gcloud auth print-identity-token --audiences="$SERVICE_URL")

curl -i -X POST "$SERVICE_URL/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "000-001",
    "message": "Can I take this medication with my current treatment?",
    "literacy_level": "medium",
    "empathy_level": "medium"
  }'
```

In some local or development setups, `gcloud auth print-identity-token` without `--audiences` may work, but the audience-specific token is the safer documented pattern for private Cloud Run.

## Testing and Validation

The repository includes focused tests that cover the important architecture boundaries.

Relevant files:

- `tests/test_imports.py`
- `tests/test_chat_refactor.py`
- `tests/test_document_rag_pipeline.py`

Areas that should be validated:

- identity split between FHIR and document RAG
- patient isolation between users
- document RAG retrieval returns chunks for the correct patient
- medication safety routing
- DailyMed target selection
- FHIR observation domain filtering
- response evidence summary structure
- debug suppression by default

## Example Flows

### 1. Current medication list question

User question:

> What drugs am I taking?

Likely sources:

- active FHIR medication list

Expected behavior:

- retrieve active medications
- do not require DailyMed labels
- do not require document RAG
- answer in a concise, patient-friendly style

### 2. Medication safety with current treatment

User question:

> Is ibuprofen safe with my current treatment?

Likely sources:

- explicit drug mention
- active FHIR medications
- allergies and conditions
- relevant observations
- DailyMed label evidence

Expected behavior:

- compare the explicit drug against current treatment
- include cautious safety wording
- mention uncertainty if evidence is incomplete
- recommend clinician or pharmacist confirmation

### 3. Question based on uploaded notes

User question:

> What did my oncology notes say about nausea?

Likely sources:

- document RAG snippets from the correct patient folder
- optional FHIR context if the planner decides it is needed

Expected behavior:

- retrieve document snippets for the correct `document_patient_id`
- summarize the relevant notes
- avoid exposing internal chunk IDs

## Developer Onboarding

If you are new to the codebase, read these files in this order:

1. `README.md`
2. `src/app.py`
3. `src/agents/orchestrator/chat_orchestrator.py`
4. `src/tools/patient/identity_map.py`
5. `src/agents/orchestrator/fhir_context_executor.py`
6. `src/tools/documents/patient_document_rag.py`
7. `src/agents/orchestrator/medication_planner.py`
8. `src/agents/orchestrator/dailymed_context_executor.py`
9. `src/agents/answer_writer/agent.py`
10. `src/agents/response_guardrail/agent.py`

### Where to make changes

| Area | File(s) |
|---|---|
| Orchestration | `src/agents/orchestrator/chat_orchestrator.py` |
| Identity resolution | `src/tools/patient/identity_map.py` |
| FHIR retrieval | `src/agents/orchestrator/fhir_context_executor.py`, `src/tools/patient/fhir_patient_context.py` |
| Document RAG | `src/tools/documents/patient_document_rag.py`, `src/tools/documents/document_rag_store.py` |
| DailyMed retrieval | `src/tools/medications/drug_lookup.py`, `src/agents/orchestrator/dailymed_context_executor.py` |
| Medication planning | `src/agents/orchestrator/medication_planner.py`, `src/agents/orchestrator/medication_plan_validator.py` |
| Response shaping | `src/app.py`, `src/agents/orchestrator/chat_orchestrator.py` |
| Prompts | `src/system_prompts/active/` |
| Agent wiring | `src/agents/orchestrator/agent.py`, `src/agents/answer_writer/agent.py`, `src/agents/response_guardrail/agent.py` |

### Safe change strategy

- keep FHIR and document identity separate
- do not assume `fhir_patient_id` is the same as `document_patient_id`
- preserve the patient isolation filter on document chunks
- keep DailyMed target selection explicit and narrow
- keep prompt changes aligned with the response guardrails
- avoid changing deployment settings unless the runtime actually requires it

## Notes

- `app.py` and `agent.py` at the repository root are compatibility entrypoints.
- `src/system_prompts/active/` is the runtime prompt source of truth; archived prompts live in `src/system_prompts/outdated/`.
- The backend is intentionally conservative: it prefers grounded, inspectable evidence over broad or speculative retrieval.
