# Ops

This folder contains runtime and deployment helpers for the medication-reasoning chatbot service.

## Kept here

- `cloud_run_client.py`: authenticated Cloud Run client for health, chat, and onboarding checks.
- `deploy_vertex.sh`: deploy helper for the ADK / Vertex-based runtime.

## Moved out

- Onboarding fixture and local demo helpers that depend on persona data now live in `../med_chatbot_webapp/scripts/`.
