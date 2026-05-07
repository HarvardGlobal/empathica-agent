# Empathica Orchestrator — Root Agent
#
# This is the only deployment entrypoint for the Empathica application.
# ADK loads `root_agent` from agent.py at the repo root, which re-exports
# this object.  Do NOT expose literacy_adaptation_agent as a root agent.
#
# Responsibilities:
#   1. Classify patient health literacy on every turn (make_literacy_decision_tool).
#   2. Detect safety and clinical-judgment overrides.
#   3. Call information tools only as needed for the specific question.
#   4. Produce a medically grounded draft — clinical accuracy takes priority.
#   5. Transfer the draft to literacy_adaptation for final communication adaptation.
#   6. Return only the literacy_adaptation agent's output to the user.
#
# Architecture note:
#   Medical grounding (steps 1–4) is separated from communication adaptation
#   (step 5) by the sub-agent boundary.  This boundary enforces that literacy
#   adaptation cannot introduce new clinical claims or remove safety content.

import os

from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext

from agents.orchestrator.literacy_control import (
    LiteracyState,
    make_literacy_decision,
    get_style_contract,
    is_meaningful_message,
    detect_safety_override,
    detect_clinical_judgment_request,
)
from agents.literacy_assessor.agent import literacy_adaptation_agent
from tools.drug_lookup import drug_lookup
from tools.patient_context import get_patient_context
from tools.allergy_check import check_allergies
from tools.literature_retrieval import retrieve_literature

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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
        "Classifies patient health literacy, retrieves drug and patient information "
        "using available tools, produces a medically grounded draft response, and "
        "delegates final communication adaptation to the literacy_adaptation sub-agent."
    ),
    instruction=open("agents/orchestrator/prompts/system.txt").read(),
    tools=[
        make_literacy_decision_tool,
        drug_lookup,
        get_patient_context,
        check_allergies,
        retrieve_literature,
    ],
    sub_agents=[
        # literacy_adaptation is the only sub-agent.
        # It receives the grounded draft and rewrites it for the patient's
        # literacy level.  It cannot add medical facts or remove warnings.
        literacy_adaptation_agent,
    ],
)
