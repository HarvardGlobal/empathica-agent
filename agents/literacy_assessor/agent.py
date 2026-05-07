# Literacy Adaptation Agent
# Receives a medically grounded draft response and the patient's detected
# health literacy level, then rewrites the draft for appropriate:
#   - vocabulary and terminology
#   - sentence length and structure
#   - explanation depth
#   - tone
#   - disclaimer wording
#
# IMPORTANT BOUNDARIES:
#   - This agent adapts communication style ONLY.
#   - It must NOT add new medical facts, diagnoses, or recommendations.
#   - It must NOT remove safety warnings, contraindications, or uncertainty.
#   - It must NOT alter the clinical meaning of the draft.
#   - It is a controlled final-response layer, not a medical decision maker.
#
# The orchestrator (empathica_orchestrator) is the root agent and the only
# deployment entrypoint.  This agent must never be exposed as a root agent.

import os

from google.adk.agents import Agent

# Prefer GOOGLE_GENAI_MODEL for Cloud Run/Vertex deployments; keep GEMINI_MODEL
# as backward-compatible fallback for existing local configs.
_MODEL = os.getenv("GOOGLE_GENAI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

literacy_adaptation_agent = Agent(
    name="literacy_adaptation",
    model=_MODEL,
    description=(
        "Adapts a medically grounded draft response for a patient's health literacy level "
        "(low / moderate / high). Rewrites vocabulary, structure, and tone without changing "
        "clinical meaning, adding new medical facts, or removing safety information."
    ),
    instruction=open("agents/literacy_assessor/prompts/system.txt").read(),
    tools=[],
    # No sub-agents: this is a terminal layer — it rewrites and returns.
    # Adding sub-agents here would risk bypassing the orchestrator's safety controls.
)
