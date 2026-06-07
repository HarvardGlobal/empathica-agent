# Architecture Decisions

## ADR-001: FastAPI as thin API wrapper

- Decision: Keep `app.py` focused on API contract and response handling.
- Reason: Clear separation between HTTP concerns and orchestration logic.

## ADR-002: ADK orchestrator as core reasoning path

- Decision: Route all `/chat` processing through `src/agents/orchestrator/chat_orchestrator.py`.
- Reason: Centralized context assembly and consistent response shape.

## ADR-003: Deterministic context selection

- Decision: Use deterministic selectors before model generation for patient/FHIR/doc context.
- Reason: Improves predictability and reduces irrelevant context injection.

## ADR-004: Environment-driven model configuration

- Decision: Set model and region via env vars (`GOOGLE_GENAI_MODEL`, `GOOGLE_CLOUD_LOCATION`).
- Reason: Enables controlled runtime changes without code edits.
