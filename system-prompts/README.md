# System Prompts

This folder is the runtime source of truth for agent and guardrail prompts.

## Versioned Prompt Registry

| Prompt file | Version | Purpose | Runtime consumers |
|---|---|---|---|
| `orchestrator_root_agent_global_safety_v1.txt` | v1 | Root orchestrator system prompt with safety and workflow rules | `agents/orchestrator/agent.py` |
| `literacy_adaptation_clinical_meaning_guardrails_v1.txt` | v1 | Literacy adaptation system prompt preserving clinical meaning | `agents/literacy_assessor/agent.py` |
| `chat_orchestrator_structured_input_template_v1.txt` | v1 | Structured input template passed to the orchestrator runner | `agents/orchestrator/chat_orchestrator.py` |
| `chat_refusal_self_harm_v1.txt` | v1 | Safety refusal response for self-harm/harmful intent | `agents/orchestrator/chat_orchestrator.py` |
| `chat_medication_safety_disclaimer_v1.txt` | v1 | Medication safety disclaimer appended for medication questions | `agents/orchestrator/chat_orchestrator.py` |
| `chat_empathy_style_low_v1.txt` | v1 | Low-empathy style contract sentence | `agents/orchestrator/chat_orchestrator.py` |
| `chat_empathy_style_medium_v1.txt` | v1 | Medium-empathy style contract sentence | `agents/orchestrator/chat_orchestrator.py` |
| `chat_empathy_style_high_v1.txt` | v1 | High-empathy style contract sentence | `agents/orchestrator/chat_orchestrator.py` |

## Naming Convention

Use descriptive filenames with this pattern:

`<component>_<purpose>_v<version>.txt`

Examples:
- `orchestrator_root_agent_global_safety_v1.txt`
- `chat_orchestrator_structured_input_template_v1.txt`

## Update Workflow

1. Edit the prompt file in this folder.
2. Keep backwards compatibility by creating a new `_vN` file only when behavior changes intentionally.
3. Update this table so the active runtime mapping stays explicit.
4. Run tests (`pytest`) to confirm guardrails and prompt wiring are intact.
