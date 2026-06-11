"""Final response guardrail checker agent."""

from google.adk.agents import Agent

from ...config import get_google_genai_model
from ...prompts_loader import load_prompt

_MODEL = get_google_genai_model()

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
