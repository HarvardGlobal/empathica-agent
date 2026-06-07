# System Prompts

This folder is the runtime source of truth for agent and guardrail prompts.
The loader in `src/prompts_loader.py` reads from `active/`.

## Active Prompt Registry

| Prompt file | Version | Purpose | Runtime consumers |
|---|---|---|---|
| `orchestrator_root_agent_global_safety_v3.txt` | v3 | Root orchestrator system prompt with safety and workflow rules | `src/agents/orchestrator/agent.py` |
| `answer_writer_medical_reasoning_v1.txt` | v1 | Reasoning and answer composition system prompt | `src/agents/answer_writer/agent.py` |
| `response_guardrail_checker_v1.txt` | v1 | Final safety and output-format checker | `src/agents/response_guardrail/agent.py` |
| `chat_orchestrator_structured_input_template_v2.txt` | v2 | Structured input template passed to the orchestrator runner | `src/agents/orchestrator/chat_orchestrator.py` |
| `chat_refusal_self_harm_v2.txt` | v2 | Safety refusal response for self-harm/harmful intent | `src/agents/orchestrator/chat_orchestrator.py` |
| `chat_medication_safety_disclaimer_v2.txt` | v2 | Medication safety disclaimer appended for medication questions | `src/agents/orchestrator/chat_orchestrator.py` |
| `chat_empathy_style_low_v2.txt` | v2 | Low-empathy style contract sentence | `src/agents/orchestrator/chat_orchestrator.py` |
| `chat_empathy_style_medium_v2.txt` | v2 | Medium-empathy style contract sentence | `src/agents/orchestrator/chat_orchestrator.py` |
| `chat_empathy_style_high_v2.txt` | v2 | High-empathy style contract sentence | `src/agents/orchestrator/chat_orchestrator.py` |

## Naming Convention

Use descriptive filenames with this pattern:

`<component>_<purpose>_v<version>.txt`

Examples:
- `orchestrator_root_agent_global_safety_v3.txt`
- `answer_writer_medical_reasoning_v1.txt`

## Outdated Prompts

Older prompt versions are kept in `outdated/` for reference and rollback history.
They are not loaded by the runtime.

## Update Workflow

1. Edit the prompt file in this folder.
2. Keep backwards compatibility by creating a new `_vN` file only when behavior changes intentionally.
3. Update this table so the active runtime mapping stays explicit.
4. Run tests (`pytest`) to confirm guardrails and prompt wiring are intact.
