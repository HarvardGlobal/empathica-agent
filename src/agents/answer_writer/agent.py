"""Patient-facing reasoning and answer composition agent."""

from google.adk.agents import Agent

from ...config import get_google_genai_model
from ...prompts_loader import load_prompt
from ..response_guardrail.agent import response_guardrail_agent

_MODEL = get_google_genai_model()

answer_writer_agent = Agent(
    name="answer_writer",
    model=_MODEL,
    description=(
        "Creates the grounded patient-facing answer from the curated orchestration package. "
        "It applies the selected literacy and empathy style while preserving medical meaning, "
        "uncertainty, and safety guidance."
    ),
    instruction=load_prompt("answer_writer_medical_reasoning_v1.txt"),
    tools=[],
    sub_agents=[response_guardrail_agent],
)
