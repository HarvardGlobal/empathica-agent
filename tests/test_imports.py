# Smoke tests — import and structural integrity checks.
#
# These tests verify the ADK application can be loaded, that agents are
# connected correctly, and that tools degrade gracefully without real backends.
# They do NOT make network calls or LLM requests.
#
# Run:  pytest tests/test_imports.py -v

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ── 1. Agent imports ──────────────────────────────────────────────────────────

class TestAgentImports:
    def test_orchestrator_imports(self):
        """empathica_orchestrator must import without error."""
        from src.agents.orchestrator.agent import root_agent
        assert root_agent is not None

    def test_answer_writer_imports(self):
        """answer_writer_agent must import without error."""
        from src.agents.answer_writer.agent import answer_writer_agent
        assert answer_writer_agent is not None

    def test_guardrail_imports(self):
        """response_guardrail_agent must import without error."""
        from src.agents.response_guardrail.agent import response_guardrail_agent
        assert response_guardrail_agent is not None

    def test_root_entrypoint_imports(self):
        """Root agent.py must expose root_agent."""
        import agent as app
        assert hasattr(app, "root_agent")
        assert app.root_agent is not None


# ── 2. Root agent identity ────────────────────────────────────────────────────

class TestRootAgentIdentity:
    def test_root_agent_is_orchestrator(self):
        """root_agent must be the empathica_orchestrator, not the literacy agent."""
        from src.agents.orchestrator.agent import root_agent
        assert root_agent.name == "empathica_orchestrator"

    def test_answer_writer_is_not_root(self):
        """answer_writer must not be exposed as root_agent anywhere."""
        from src.agents.answer_writer.agent import answer_writer_agent
        assert answer_writer_agent.name != "empathica_orchestrator"

    def test_guardrail_is_not_root(self):
        """response_guardrail must not be exposed as root_agent anywhere."""
        from src.agents.response_guardrail.agent import response_guardrail_agent
        assert response_guardrail_agent.name != "empathica_orchestrator"

    def test_answer_writer_name(self):
        from src.agents.answer_writer.agent import answer_writer_agent
        assert answer_writer_agent.name == "answer_writer"

    def test_guardrail_name(self):
        from src.agents.response_guardrail.agent import response_guardrail_agent
        assert response_guardrail_agent.name == "response_guardrail_checker"


# ── 3. Orchestrator → answer_writer / guardrail connection ───────────────────

class TestAgentConnections:
    def test_orchestrator_has_answer_writer_sub_agent(self):
        """empathica_orchestrator must reference answer_writer as a sub-agent."""
        from src.agents.orchestrator.agent import root_agent
        from src.agents.answer_writer.agent import answer_writer_agent
        sub_agent_names = [a.name for a in root_agent.sub_agents]
        assert "answer_writer" in sub_agent_names, (
            f"answer_writer not found in orchestrator sub_agents: {sub_agent_names}"
        )

    def test_orchestrator_references_correct_sub_agent_object(self):
        from src.agents.orchestrator.agent import root_agent
        from src.agents.answer_writer.agent import answer_writer_agent
        assert answer_writer_agent in root_agent.sub_agents

    def test_answer_writer_has_guardrail_sub_agent(self):
        """answer_writer must reference response_guardrail_checker as a sub-agent."""
        from src.agents.answer_writer.agent import answer_writer_agent
        from src.agents.response_guardrail.agent import response_guardrail_agent
        sub_agent_names = [a.name for a in answer_writer_agent.sub_agents]
        assert "response_guardrail_checker" in sub_agent_names
        assert response_guardrail_agent in answer_writer_agent.sub_agents

    def test_guardrail_has_no_sub_agents(self):
        """response_guardrail_checker must be a terminal layer with no sub-agents."""
        from src.agents.response_guardrail.agent import response_guardrail_agent
        assert len(response_guardrail_agent.sub_agents) == 0


# ── 4. Tool imports ───────────────────────────────────────────────────────────

class TestToolImports:
    def test_drug_lookup_imports(self):
        from src.tools.medications.drug_lookup import drug_lookup
        assert callable(drug_lookup)

    def test_patient_context_imports(self):
        from src.tools.patient.patient_context import get_patient_context
        assert callable(get_patient_context)

    def test_orchestrator_tools_include_active_runtime_tools(self):
        from src.agents.orchestrator.agent import root_agent
        tool_names = {t.__name__ for t in root_agent.tools}
        assert "drug_lookup" in tool_names
        assert "get_patient_context" in tool_names


# ── 5. Tool graceful degradation (no backend wired) ──────────────────────────

class TestToolGracefulDegradation:
    """
    Tools must return a structured failure dict when backends are unavailable.
    They must never raise an uncaught exception when env vars are not set.
    """

    def test_drug_lookup_uses_dailymed_without_env(self, monkeypatch):
        import src.tools.medications.drug_lookup as m
        monkeypatch.delenv("DRUG_KNOWLEDGE_API_URL", raising=False)
        monkeypatch.setattr(
            m,
            "_resolve_from_drug_name",
            lambda _: (
                {"setid": "set-id-1", "title": "Ibuprofen", "published_date": "2026-01-01"},
                None,
                False,
            ),
        )
        monkeypatch.setattr(
            m,
            "_fetch_label_context_by_setid",
            lambda setid, title_hint=None: {
                "ok": True,
                "setid": setid,
                "title": title_hint,
                "context": "DailyMed label context",
            },
        )
        result = m.drug_lookup("ibuprofen")
        assert result["status"] == "ok"
        assert result["setid"] == "set-id-1"
        assert "label_context" in result

    def test_patient_context_unavailable_without_env(self, monkeypatch):
        import src.tools.patient.patient_context as m
        monkeypatch.setattr(m, "_API_URL", "")
        result = m.get_patient_context("patient-123")
        assert result["status"] == "unavailable"
        assert "message" in result


# ── 6. Literacy control logic ─────────────────────────────────────────────────

class TestLiteracyControl:
    def test_make_literacy_decision_imports(self):
        from src.agents.orchestrator.literacy_control import make_literacy_decision
        assert callable(make_literacy_decision)

    def test_make_literacy_decision_tool_imports(self):
        from src.agents.orchestrator.agent import make_literacy_decision_tool
        assert callable(make_literacy_decision_tool)

    def test_make_literacy_decision_tool_returns_dict(self):
        """Tool works without a ToolContext (tool_context=None, session state skipped)."""
        from src.agents.orchestrator.agent import make_literacy_decision_tool
        result = make_literacy_decision_tool("What is this pill for?")
        assert isinstance(result, dict)
        assert "literacy_level" in result
        assert result["literacy_level"] in {"low", "moderate", "high"}

    def test_safety_override_triggers_on_emergency(self):
        from src.agents.orchestrator.agent import make_literacy_decision_tool
        result = make_literacy_decision_tool("I am having trouble breathing and chest pain")
        assert result["safety_override"] is True
        assert result["literacy_level"] == "low"

    def test_clinical_judgment_override_on_personal_decision(self):
        from src.agents.orchestrator.agent import make_literacy_decision_tool
        result = make_literacy_decision_tool("Should I stop taking this medication?")
        assert result["clinical_judgment_override"] is True

    def test_session_state_persisted_across_turns(self):
        """
        Simulate two turns: the tool should write state on turn 1 and reuse it
        on turn 2, with the level remaining consistent rather than re-classifying
        from scratch.
        """
        from src.agents.orchestrator.agent import make_literacy_decision_tool, _LITERACY_STATE_KEY

        # Minimal ToolContext stub — just a dict-backed state store.
        class FakeToolContext:
            state: dict = {}

        ctx = FakeToolContext()

        # Turn 1: first message — state is empty, tool classifies from scratch.
        r1 = make_literacy_decision_tool("What is this pill for?", tool_context=ctx)
        assert _LITERACY_STATE_KEY in ctx.state, "Tool must write literacy state to session"
        level_after_t1 = r1["literacy_level"]

        # Turn 2: second message — tool should read persisted state.
        r2 = make_literacy_decision_tool("Will it hurt my stomach?", tool_context=ctx)
        # Level should be consistent (same signal type), not reset to default.
        assert r2["literacy_level"] == level_after_t1, (
            "Stable literacy level should be reused across turns"
        )

    def test_stable_level_not_reclassified(self):
        """
        After enough consistent messages the status should become 'stable',
        and trivial follow-ups should not change the level.
        """
        from src.agents.orchestrator.agent import make_literacy_decision_tool

        class FakeToolContext:
            state: dict = {}

        ctx = FakeToolContext()

        # Three clear low-literacy messages to reach stability.
        for msg in [
            "What is this pill for?",
            "Will it hurt my stomach?",
            "Is it safe?",
        ]:
            make_literacy_decision_tool(msg, tool_context=ctx)

        # After stability, a trivial acknowledgement should not reclassify.
        r = make_literacy_decision_tool("Okay thanks.", tool_context=ctx)
        assert r["literacy_level"] == "low"


# ── 7. Literacy adaptation preserves clinical content (unit-level check) ──────

class TestLiteracyAdaptationSafety:
    """
    The adaptation agent's system prompt is checked for key safety constraints.
    These tests verify the prompt file contains the required guardrail language
    so that a prompt regression will be caught immediately.
    """

    def _read_prompt(self) -> str:
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "..", "src", "system_prompts", "active", "answer_writer_medical_reasoning_v1.txt"
        )
        with open(os.path.normpath(prompt_path)) as f:
            return f.read()

    def test_prompt_forbids_adding_new_medical_facts(self):
        prompt = self._read_prompt()
        assert "Do NOT add new medical facts" in prompt or "not add new medical" in prompt.lower()

    def test_prompt_forbids_removing_safety_warnings(self):
        prompt = self._read_prompt()
        assert "Do NOT remove safety warnings" in prompt or "not remove safety" in prompt.lower()

    def test_prompt_forbids_altering_clinical_meaning(self):
        prompt = self._read_prompt()
        assert "clinical meaning" in prompt.lower()

    def test_prompt_requires_disclaimer(self):
        prompt = self._read_prompt()
        assert "disclaimer" in prompt.lower()

    def test_prompt_covers_all_three_literacy_levels(self):
        prompt = self._read_prompt()
        assert "LOW LITERACY" in prompt or "low literacy" in prompt.lower()
        assert "MODERATE LITERACY" in prompt or "moderate literacy" in prompt.lower()
        assert "HIGH LITERACY" in prompt or "high literacy" in prompt.lower()
