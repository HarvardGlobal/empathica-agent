# Architecture Overview

## System summary

The service is a FastAPI application deployed to Cloud Run. It processes `POST /chat` requests and delegates response generation to an ADK orchestrator agent, which coordinates retrieval and context tools.

## Request flow

1. Client sends `POST /chat` request to Cloud Run service.
2. `app.py` validates the payload and invokes the orchestrator flow.
3. `agents/orchestrator/chat_orchestrator.py` assembles structured context blocks.
4. ADK `Runner` executes `root_agent` from `agent.py`.
5. The orchestrator agent generates response text and literacy/empathy controls.
6. API returns normalized JSON contract to the client.

## Main components

- API layer: `app.py`
- ADK root agent entrypoint: `agent.py`
- Orchestrator logic: `agents/orchestrator/chat_orchestrator.py`
- Literacy adaptation sub-agent: `agents/literacy_assessor/*`
- Retrieval and context tools: `tools/*`

## External dependencies

- Vertex AI (Gemini model inference)
- DailyMed API (drug label context)
- Google Cloud Healthcare API / FHIR store (optional patient context)
- Google Cloud Storage (optional patient document snippets)

## Runtime data boundaries

- Stateless API container in Cloud Run.
- Persistent data remains in external managed services (FHIR and GCS).
- No patient data should be written to local container filesystem.
