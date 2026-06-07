from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

Priority = Literal["required", "optional"]
RiskLevel = Literal["low", "moderate", "high", "urgent", "unknown"]


@dataclass
class PlanContextItem:
    domain: str
    reason: str
    priority: Priority
    lookback_days: int | None = None


@dataclass
class RetrievalPlan:
    intent: str
    question_type: str
    risk_level: RiskLevel
    requires_patient_specific_context: bool
    required_context: list[PlanContextItem] = field(default_factory=list)
    optional_context: list[PlanContextItem] = field(default_factory=list)
    do_not_fetch: list[dict[str, str]] = field(default_factory=list)
    missing_information_questions: list[str] = field(default_factory=list)
    safety_flags: list[str] = field(default_factory=list)
    planner_rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "question_type": self.question_type,
            "risk_level": self.risk_level,
            "requires_patient_specific_context": self.requires_patient_specific_context,
            "required_context": [asdict(item) for item in self.required_context],
            "optional_context": [asdict(item) for item in self.optional_context],
            "do_not_fetch": self.do_not_fetch,
            "missing_information_questions": self.missing_information_questions,
            "safety_flags": self.safety_flags,
            "planner_rationale": self.planner_rationale,
        }
