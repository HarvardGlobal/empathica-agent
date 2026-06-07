"""Root ADK agent for the medication reasoning chatbot."""

import os

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext

from ...prompts_loader import load_prompt
from .literacy_control import (
    LiteracyState,
    make_literacy_decision,
)
from ..answer_writer.agent import answer_writer_agent
from ...tools.medications.drug_lookup import drug_lookup
from ...tools.patient.patient_context import get_patient_context

# Prefer GOOGLE_GENAI_MODEL for Cloud Run/Vertex deployments; keep GEMINI_MODEL
# as backward-compatible fallback for existing local configs.
_MODEL = os.getenv("GOOGLE_GENAI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

# Session state key where the LiteracyState is persisted between turns.
# Using a namespaced key avoids collisions with other session state values.
_LITERACY_STATE_KEY = "empathica_literacy_state"


def make_literacy_decision_tool(
    current_message: str,
    patient_name: str | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """
    Classify the patient's health literacy level and return a full decision
    object (style contract, disclaimer type, safety overrides).

    Session state is managed automatically:
      - On the first call, classification runs from scratch.
      - Once the literacy level is marked "stable" (typically after 2+ meaningful
        messages with consistent signals), it is reused in subsequent turns without
        re-running the full scorer — saving computation.
      - The level is only re-evaluated if the patient's messages show a significant
        literacy drift (e.g. vocabulary suddenly shifts level by > 0.3 probability).

    Call this on EVERY turn before generating any response content.
    You do NOT need to pass or track literacy state yourself — the tool handles it.

    Parameters
    ----------
    current_message : str
        The patient's latest message verbatim.
    patient_name : str | None
        Patient's first name for personalised disclaimer wording.
    tool_context : ToolContext
        Injected automatically by ADK. Provides access to session state for
        persisting the LiteracyState across turns.

    Returns
    -------
    dict
        Full LiteracyDecision as a plain dict.  Fields include:
        literacy_level, literacy_confidence, literacy_status, recheck_required,
        reasoning_summary, style_contract, disclaimer_type,
        response_structure_required, safety_override, clinical_judgment_override.
    """
    # Read persisted LiteracyState from session (None on first turn).
    state_dict = None
    if tool_context is not None:
        state_dict = tool_context.state.get(_LITERACY_STATE_KEY)

    state = LiteracyState.from_dict(state_dict) if state_dict else None
    decision = make_literacy_decision(current_message, state, patient_name)

    # Persist the updated state so the next turn can reuse a stable classification.
    if tool_context is not None:
        tool_context.state[_LITERACY_STATE_KEY] = decision.updated_state.to_dict()

    return decision.to_dict()


root_agent = Agent(
    name="empathica_orchestrator",
    model=_MODEL,
    description=(
        "Root agent for the Empathica medication reasoning chatbot. "
        "Classifies patient health literacy, retrieves drug and patient information, "
        "plans medication evidence, packages the curated context, and delegates answer drafting to the answer_writer "
        "and final safety checking to the response_guardrail_checker sub-agent."
    ),
    instruction=load_prompt("orchestrator_root_agent_global_safety_v3.txt"),
    tools=[
        make_literacy_decision_tool,
        drug_lookup,
        get_patient_context,
    ],
    sub_agents=[
        answer_writer_agent,
    ],
)
