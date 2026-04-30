# tools/ — ADK tool functions available to empathica_orchestrator.
#
# Each tool is a plain Python callable that ADK wraps and exposes to the
# orchestrator's LLM. Tools are responsible for retrieving external data;
# they do NOT perform clinical reasoning.
#
# Wiring a real backend: replace the stub body in each module with a call to
# your actual service (database, API, vector store, etc.).  Environment
# variables for each service are documented in .env.example.
