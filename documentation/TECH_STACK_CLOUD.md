# Cloud Development Tech Stack — Empathica Medication Reasoning Chatbot

## Core AI & ML Framework

| Technology | Version | Purpose |
|---|---|---|
| **Google ADK** (Agent Development Kit) | ≥1.28.1 | Multi-agent orchestration framework for Gemini/Vertex AI agentic workflows |
| **Google Gemini** | 2.5-flash (configurable) | Foundational LLM for reasoning, medication safety analysis, and conversational logic |
| **Vertex AI** | Latest | Google Cloud's enterprise AI platform for model deployment, scaling, and API management |

---

## Python Runtime & Web Framework

| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.11 | Slim containerized runtime for performance and security |
| **FastAPI** | ≥0.115.0 | Async HTTP API framework for Cloud Run services |
| **Uvicorn** | ≥0.30.0 | ASGI server for FastAPI; runs on port 8080 inside container |
| **Pydantic** | (via FastAPI) | Type validation, schema definition, and API request/response models |

---

## Google Cloud Services

| Service | Configuration | Purpose |
|---|---|---|
| **Cloud Run** | Managed, auto-scaling | Containerized deployment of orchestrator agent API |
| **Vertex AI Platform** | US-East4 region | Model serving, agent lifecycle, and inference scaling |
| **Cloud Firestore** | empathica-identity-map (database) | Patient identity mapping and persistent user session data |
| **Cloud Storage** | empathica-patient-documents-dev bucket | Document retrieval and medical record storage |
| **FHIR Store** | empathica_fhir_store (Healthcare Data Engine) | FHIR-compliant patient context and clinical records |
| **Artifact Registry** | agents (repository) | Private Docker image registry for agent containers |
| **Cloud Build** | CI/CD pipeline | Automated build, test, and deployment workflow |

---

## Cloud Authentication & Security

| Component | Details |
|---|---|
| **Service Accounts** | empathica-agent-runtime-447 (runtime permissions) |
| **IAM Roles** | Firestore read/write, Cloud Storage access, FHIR read |
| **API Keys** | Environment variable-driven (GOOGLE_GENAI_MODEL, GOOGLE_CLOUD_LOCATION) |
| **Environment Files** | .env configuration for local development & secrets management |

---

## Containerization & Orchestration

| Technology | Purpose |
|---|---|
| **Docker** | Container image build (Dockerfile: Python 3.11-slim + dependencies) |
| **Cloud Build Steps** | (1) Docker build → (2) Push to Artifact Registry → (3) Deploy to Cloud Run |
| **Port Configuration** | 8080 (containerized service port) |
| **Non-root User** | appuser (UID 10001) for security best practices |

---

## Medical & Clinical Tools

| Module | Source | Purpose |
|---|---|---|
| **FHIR Patient Context** | `src/tools/patient/fhir_patient_context.py` | Query FHIR store for patient clinical history |
| **Patient Document Retrieval** | `src/tools/documents/patient_document_retrieval.py` | Fetch medical documents from Cloud Storage |
| **Patient Context Selector** | `src/tools/patient/patient_context_selector.py` | Intelligent selection of relevant patient data |
| **Drug Lookup** | `src/tools/medications/drug_lookup.py` | DailyMed API integration for medication information |
| **Identity Map** | `src/tools/patient/identity_map.py` | De-identification and patient identity resolution via Firestore |

---

## Multi-Agent Orchestration

| Agent | Purpose | Deployment |
|---|---|---|
| **Orchestrator (root_agent)** | Main chat coordinator, safety enforcement, literacy routing | Primary Cloud Run service |
| **Literacy Assessor** | Reading level evaluation and content adaptation | Controlled sub-agent |
| **Chat Orchestrator** | Request routing, structured input processing, context window management | Sub-agent of orchestrator |

---

## Agent Customization & Prompting

| Artifact | Count | Purpose |
|---|---|---|
| **System Prompts** | 8 versioned files | Empathy levels (low/medium/high), safety disclaimers, guardrails, structured templates |
| **Framework Documents** | Literacy adaptation framework | Clinical meaning preservation during simplification |
| **Prompt Versioning** | v1/v2 variants | A/B testing and iterative improvement |

---

## Testing & Quality Assurance

| Tool | Version | Purpose |
|---|---|---|
| **Pytest** | ≥8.0.0 | Unit and integration testing framework |
| **Test Suite** | tests/ directory | Import validation, literacy scoring, document retrieval, patient context selection |

---

## HTTP & External Communication

| Library | Version | Purpose |
|---|---|---|
| **httpx** | ≥0.27.0 | HTTP client for backend tool integrations (drug lookup, FHIR, document retrieval) |
| **python-multipart** | ≥0.0.9 | Handle multipart form data for file uploads (patient documents, onboarding) |

---

## Development & Environment Management

| Tool | Purpose |
|---|---|
| **python-dotenv** | ≥1.0.0 | Load .env files for local development without committing secrets |
| **.env.example** | Template for required environment variables |
| **Virtual Environment** | .venv isolation (activate: source .venv/bin/activate) |

---

## Deployment Pipeline

```
GitHub Push (main branch)
    ↓
Cloud Build Trigger
    ↓
[1] Docker build from Dockerfile (Python 3.11-slim + deps)
    ↓
[2] Push to Artifact Registry (us-east4-docker.pkg.dev)
    ↓
[3] Deploy to Cloud Run (managed, auto-scaling)
    ↓
Set Env Vars (model, location, GCP project, FHIR config)
    ↓
Cloud Run Service (port 8080, no public auth required)
```

---

## CI/CD Configuration

| Variable | Example Value | Purpose |
|---|---|---|
| _REGION | us-east4 | GCP region for all services |
| _SERVICE | empathica-agents | Cloud Run service name |
| _FHIR_PROJECT_ID | dci-chatbot-476416 | GCP project for healthcare data |
| _FHIR_STORE | empathica_fhir_store | FHIR Healthcare Data Engine store |
| _PATIENT_DOCS_BUCKET | empathica-patient-documents-dev-* | Cloud Storage for medical documents |
| _FIRESTORE_DATABASE_ID | empathica-identity-map | Firestore database for identity mapping |

---

## Architecture Summary

**Pattern:** Multi-agent agentic system with tool-use orchestration

- **Entry Point:** FastAPI HTTP endpoint (app.py)
- **Agent Logic:** Google ADK orchestrator agent managing sub-agents
- **Tool Layer:** Clinical tools (FHIR, drug lookup, document retrieval)
- **State Management:** Firestore (patient identity, session persistence)
- **Model Backend:** Vertex AI (Gemini inference)
- **Deployment:** Containerized on Cloud Run with auto-scaling
- **CI/CD:** Cloud Build (build → registry → deploy pipeline)
