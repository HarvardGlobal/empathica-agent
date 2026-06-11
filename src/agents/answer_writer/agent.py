"""Patient-facing reasoning and answer composition agent."""

import os

from google.adk.agents import Agent

from ...prompts_loader import load_prompt
from ..response_guardrail.agent import response_guardrail_agent

_MODEL = os.getenv("GOOGLE_GENAI_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.5-flash"))

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
