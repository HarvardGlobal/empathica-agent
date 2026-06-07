"""Final response guardrail checker agent."""

import os

from google.adk.agents import Agent

from ...prompts_loader import load_prompt

_MODEL = os.getenv("GOOGLE_GENAI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))

response_guardrail_agent = Agent(
    name="response_guardrail_checker",
    model=_MODEL,
    description=(
        "Validates the drafted answer against safety, privacy, and output-format guardrails. "
        "It may minimally repair the final JSON response but does not make new medical decisions."
    ),
    instruction=load_prompt("response_guardrail_checker_v1.txt"),
    tools=[],
    sub_agents=[],
)
