# Root ADK entrypoint — Empathica medication reasoning chatbot.
#
# ADK locates the application by importing `root_agent` from this file.
# Run locally:   adk run .
# Deploy:        adk deploy .
#
# The root agent is `empathica_orchestrator`.
# The `literacy_adaptation` agent is wired as a controlled sub-agent of the
# orchestrator and is NOT an independent deployment target.
#
# See agents/orchestrator/agent.py for the full agent definition.
# See .env.example for required environment variables.

from agents.orchestrator.agent import root_agent  # noqa: F401 — re-exported for ADK

__all__ = ["root_agent"]
