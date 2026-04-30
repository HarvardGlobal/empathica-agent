# Orchestrator — Health Literacy Control Logic
#
# This module is the single source of truth for all literacy-related decisions
# in the orchestrator pipeline. It:
#   1. Classifies literacy level from the current message + conversation history
#   2. Maintains LiteracyState across a conversation
#   3. Detects safety overrides and clinical-judgment requests
#   4. Produces a LiteracyDecision — the full contract passed to answer-generation agents
#
# Uses scorer.py (deterministic layer) as the primary classification signal.
# The LLM-based literacy_assessor_agent handles edge cases the scorer cannot.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from agents.literacy_assessor.scorer import (
    LEVELS,
    MessageScore,
    assess_session,
    score_message,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STABILITY_THRESHOLD = 0.5          # final_confidence >= this → stable
_MIN_MEANINGFUL_FOR_STABLE = 2      # need at least this many meaningful msgs before locking
_DEFAULT_LEVEL = "moderate"         # fallback when signal is absent or ambiguous

# Minimum word count for a message to count as meaningful for literacy estimation
_MEANINGFUL_MIN_WORDS = 3

# Trivial acknowledgement patterns that carry no literacy signal
_TRIVIAL_PATTERNS = re.compile(
    r'^\s*(ok|okay|thanks|thank you|yes|no|sure|yep|nope|got it|alright|great|cool'
    r'|sounds good|what about this|hmm|hm|mm|understood)\s*[.!?]?\s*$',
    re.IGNORECASE,
)

# Safety-critical terms that trigger emergency override
_SAFETY_SIGNALS = [
    "trouble breathing", "can't breathe", "cannot breathe", "difficulty breathing",
    "chest pain", "chest tightness",
    "face swelling", "lip swelling", "tongue swelling", "throat swelling",
    "severe allergic", "anaphylaxis",
    "suicidal", "want to die", "kill myself", "end my life",
    "unconscious", "passed out", "not breathing",
    "911", "call emergency",
]

# Clinical-judgment request patterns — require hard override disclaimer
_CLINICAL_JUDGMENT_PATTERNS = [
    r'\bshould i\b',
    r'\bdo i need\b',
    r'\bcan i take this\b',
    r'\bis it safe\b',
    r'\bis this normal\b',
    r'\bdo i need this medication\b',
    r'\bshould i stop\b',
    r'\bshould i start\b',
    r'\bam i taking too much\b',
    r'\bwhat dose should\b',
    r'\bwhich medication should\b',
    r'\bshould i switch\b',
]
_CLINICAL_JUDGMENT_RE = re.compile(
    '|'.join(_CLINICAL_JUDGMENT_PATTERNS), re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class StyleContract:
    """Writing constraints for a specific literacy level."""
    tone: str
    language: str
    structure: str
    disclaimer_standard: str
    disclaimer_clinical_judgment: str
    mixing_allowed: bool = False


@dataclass
class LiteracyState:
    """
    Persisted across a conversation. Updated after every meaningful message.
    Serialise to / deserialise from ADK session state as a plain dict.
    """
    level: str = _DEFAULT_LEVEL
    confidence: float = 0.0
    status: str = "unstable"            # "unstable" | "stable"
    meaningful_message_count: int = 0
    message_history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "confidence": self.confidence,
            "status": self.status,
            "meaningful_message_count": self.meaningful_message_count,
            "message_history": self.message_history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LiteracyState":
        return cls(
            level=d.get("level", _DEFAULT_LEVEL),
            confidence=d.get("confidence", 0.0),
            status=d.get("status", "unstable"),
            meaningful_message_count=d.get("meaningful_message_count", 0),
            message_history=d.get("message_history", []),
        )


@dataclass
class LiteracyDecision:
    """
    Full decision object output by make_literacy_decision().
    Passed to every downstream answer-generation agent.
    """
    literacy_level: str
    literacy_confidence: float
    literacy_status: str
    recheck_required: bool
    reasoning_summary: list[str]
    style_contract: StyleContract
    disclaimer_type: str                # "standard" | "clinical_judgment"
    response_structure_required: list[str]
    safety_override: bool
    clinical_judgment_override: bool
    updated_state: LiteracyState

    def to_dict(self) -> dict:
        """Serialise to a plain dict for passing through ADK tool boundaries."""
        return {
            "literacy_level": self.literacy_level,
            "literacy_confidence": self.literacy_confidence,
            "literacy_status": self.literacy_status,
            "recheck_required": self.recheck_required,
            "reasoning_summary": self.reasoning_summary,
            "style_contract": {
                "tone": self.style_contract.tone,
                "language": self.style_contract.language,
                "structure": self.style_contract.structure,
                "disclaimer_standard": self.style_contract.disclaimer_standard,
                "disclaimer_clinical_judgment": self.style_contract.disclaimer_clinical_judgment,
                "mixing_allowed": self.style_contract.mixing_allowed,
            },
            "disclaimer_type": self.disclaimer_type,
            "response_structure_required": self.response_structure_required,
            "safety_override": self.safety_override,
            "clinical_judgment_override": self.clinical_judgment_override,
        }


# ---------------------------------------------------------------------------
# Style contracts — one per literacy level
# ---------------------------------------------------------------------------

_STYLE_CONTRACTS: dict[str, StyleContract] = {
    "low": StyleContract(
        tone="warm, supportive, emotionally reassuring",
        language=(
            "everyday words only — no jargon; concrete explanations; "
            "simple familiar terms; translate any medical term immediately into plain language"
        ),
        structure=(
            "short sentences (target 5–12 words); bullets encouraged; "
            "one idea at a time; avoid mechanistic or drug-class detail"
        ),
        disclaimer_standard=(
            "Always talk to your doctor or pharmacist."
        ),
        disclaimer_clinical_judgment=(
            "Please tell Sarah so she can call your doctor or pharmacist right away, okay?"
        ),
    ),
    "moderate": StyleContract(
        tone="calm, clear, respectful",
        language=(
            "basic medical terms allowed; briefly explain each term on first use; "
            "balanced clarity — not too simple, not too technical"
        ),
        structure=(
            "short paragraphs or bullets; simple headings such as Purpose, "
            "How It Works, Side Effects; keep grounded and accessible"
        ),
        disclaimer_standard=(
            "Consult your healthcare provider for personalized advice."
        ),
        disclaimer_clinical_judgment=(
            "Please discuss this with your doctor or pharmacist — Sarah can help you call them today."
        ),
    ),
    "high": StyleContract(
        tone="concise, technical, professional",
        language=(
            "advanced medical terminology allowed; mechanistic detail permitted; "
            "evidence-based framing allowed; may reference FDA warnings or clinical principles"
        ),
        structure=(
            "organised headings: Indications, Mechanism, Adverse Effects, "
            "Contraindications, Monitoring; professional density without being unsafe"
        ),
        disclaimer_standard=(
            "Consult a healthcare provider for individualized treatment plans."
        ),
        disclaimer_clinical_judgment=(
            "Please discuss this with your doctor or pharmacist — Sarah can help you call them today."
        ),
    ),
}

# Required response sections (same order for all levels)
_RESPONSE_STRUCTURE = [
    "empathy_and_validation",
    "clear_explanation",
    "persona_personalization",
    "safety_framing",
    "disclaimer",
]


# ---------------------------------------------------------------------------
# Signal detection helpers
# ---------------------------------------------------------------------------

def is_meaningful_message(text: str) -> bool:
    """
    A message is meaningful for literacy estimation only if it carries enough
    linguistic signal: medication vocabulary, question structure, or sentence
    complexity. Trivial acknowledgements and single-word replies are excluded.
    """
    stripped = text.strip()
    if _TRIVIAL_PATTERNS.match(stripped):
        return False
    words = stripped.split()
    if len(words) < _MEANINGFUL_MIN_WORDS:
        return False
    # Score it — if the scorer finds no vocab matches and no intent signals
    # it is likely too weak to classify
    msg_score = score_message(stripped)
    total_vocab = sum(msg_score.vocab_counts.values())
    has_intent = any(v > 0 for v in msg_score.intent_flags.values())
    return total_vocab > 0 or has_intent or len(words) >= 6


def detect_safety_override(text: str) -> bool:
    """Return True if the message contains emergency / safety-critical signals."""
    t = text.lower()
    return any(signal in t for signal in _SAFETY_SIGNALS)


def detect_clinical_judgment_request(text: str) -> bool:
    """Return True if the message requests individualized clinical judgment."""
    return bool(_CLINICAL_JUDGMENT_RE.search(text))


# ---------------------------------------------------------------------------
# Core classification logic
# ---------------------------------------------------------------------------

def _classify_from_history(
    message_history: list[str],
    current_message: str,
) -> tuple[str, float, list[str]]:
    """
    Run the deterministic scorer over all meaningful messages and return
    (level, confidence, reasoning_bullets).
    """
    meaningful = [m for m in message_history if is_meaningful_message(m)]
    if is_meaningful_message(current_message):
        meaningful.append(current_message)

    if not meaningful:
        return _DEFAULT_LEVEL, 0.0, ["no meaningful message signal — defaulting to moderate"]

    session = assess_session(meaningful)
    reasoning: list[str] = []

    # Current message score for single-message reasoning
    current_score: MessageScore = score_message(current_message)
    top_probs = sorted(current_score.probabilities.items(), key=lambda x: x[1], reverse=True)
    reasoning.append(
        f"current message scored as {current_score.level} "
        f"(p={current_score.probabilities[current_score.level]:.2f})"
    )
    if sum(current_score.vocab_counts.values()) > 0:
        dominant_class = max(current_score.vocab_counts, key=current_score.vocab_counts.__getitem__)
        reasoning.append(f"strongest vocabulary signal: {dominant_class}")
    if any(v > 0 for v in current_score.intent_flags.values()):
        intent_hit = [k for k, v in current_score.intent_flags.items() if v > 0]
        reasoning.append(f"intent signals matched: {', '.join(intent_hit)}")
    reasoning.append(
        f"session majority={session.level}, "
        f"consistency={session.consistency:.2f}, "
        f"final_confidence={session.final_confidence:.2f}"
    )

    return session.level, session.final_confidence, reasoning


def _should_recheck(state: LiteracyState, current_score: MessageScore) -> bool:
    """
    Decide whether literacy should be reassessed.
    Recheck if:
    - session is not yet stable, OR
    - the current message level differs substantially from the stored level
    """
    if state.status == "unstable":
        return True
    # Meaningful level shift: current message strongly disagrees with stored level
    stored_prob = current_score.probabilities.get(state.level, 0.0)
    current_top_prob = max(current_score.probabilities.values())
    if current_top_prob - stored_prob > 0.3:
        return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def make_literacy_decision(
    current_message: str,
    state: Optional[LiteracyState] = None,
    patient_name: Optional[str] = None,
) -> LiteracyDecision:
    """
    Main entry point called by the orchestrator on every user turn.

    Parameters
    ----------
    current_message:
        The raw text of the patient's latest message.
    state:
        The LiteracyState carried over from the previous turn.
        Pass None for the first message in a session.
    patient_name:
        Optional name for personalised disclaimer wording.

    Returns
    -------
    LiteracyDecision
        The full decision object containing the literacy level, confidence,
        style contract, disclaimer type, and updated state.
    """
    if state is None:
        state = LiteracyState()

    # ── Safety override check (highest priority) ──────────────────────────
    safety_override = detect_safety_override(current_message)
    if safety_override:
        updated_state = LiteracyState(
            level="low",  # safety messages always use simplest language
            confidence=1.0,
            status=state.status,
            meaningful_message_count=state.meaningful_message_count,
            message_history=state.message_history + [current_message],
        )
        return LiteracyDecision(
            literacy_level="low",
            literacy_confidence=1.0,
            literacy_status=updated_state.status,
            recheck_required=False,
            reasoning_summary=["SAFETY OVERRIDE — emergency signal detected"],
            style_contract=_STYLE_CONTRACTS["low"],
            disclaimer_type="clinical_judgment",
            response_structure_required=["empathy_and_validation", "urgent_safety_guidance", "disclaimer"],
            safety_override=True,
            clinical_judgment_override=False,
            updated_state=updated_state,
        )

    # ── Clinical judgment override check ──────────────────────────────────
    clinical_judgment_override = detect_clinical_judgment_request(current_message)

    # ── Literacy classification ────────────────────────────────────────────
    is_meaningful = is_meaningful_message(current_message)
    current_score = score_message(current_message)

    # Decide whether to reclassify or reuse stored level
    recheck = _should_recheck(state, current_score)

    if recheck and is_meaningful:
        new_history = state.message_history + [current_message]
        level, confidence, reasoning = _classify_from_history(
            state.message_history, current_message
        )
    else:
        # Reuse stored level — message too weak or session already stable
        new_history = state.message_history + ([current_message] if is_meaningful else [])
        level = state.level
        confidence = state.confidence
        reasoning = [
            f"reusing stored level '{state.level}' (confidence={state.confidence:.2f})",
            "current message signal insufficient for reclassification" if not is_meaningful
            else "session already stable — no drift detected",
        ]

    # ── Guardrails ────────────────────────────────────────────────────────
    # Technical terms used incorrectly → demote to moderate
    if level == "high" and current_score.level != "high":
        # Scorer's per-message verdict contradicts session: borderline misuse
        if current_score.probabilities.get("high", 0) < 0.35:
            reasoning.append(
                "technical terms may be used incorrectly — "
                "demoting to moderate per guardrail rule"
            )
            level = "moderate"
            confidence = min(confidence, 0.6)

    # Unknown or empty level → fallback
    if level not in LEVELS:
        level = _DEFAULT_LEVEL
        reasoning.append(f"unknown level value — defaulted to {_DEFAULT_LEVEL}")

    # ── Update state ──────────────────────────────────────────────────────
    new_meaningful_count = (
        state.meaningful_message_count + (1 if is_meaningful else 0)
    )
    is_stable = (
        confidence >= _STABILITY_THRESHOLD
        and new_meaningful_count >= _MIN_MEANINGFUL_FOR_STABLE
    )
    updated_state = LiteracyState(
        level=level,
        confidence=confidence,
        status="stable" if is_stable else "unstable",
        meaningful_message_count=new_meaningful_count,
        message_history=new_history[-20:],  # cap history to last 20 messages
    )

    # ── Disclaimer type ───────────────────────────────────────────────────
    disclaimer_type = "clinical_judgment" if clinical_judgment_override else "standard"

    return LiteracyDecision(
        literacy_level=level,
        literacy_confidence=round(confidence, 4),
        literacy_status=updated_state.status,
        recheck_required=not is_stable,
        reasoning_summary=reasoning,
        style_contract=_STYLE_CONTRACTS[level],
        disclaimer_type=disclaimer_type,
        response_structure_required=_RESPONSE_STRUCTURE,
        safety_override=False,
        clinical_judgment_override=clinical_judgment_override,
        updated_state=updated_state,
    )


def get_style_contract(level: str) -> StyleContract:
    """Return the StyleContract for a given level. Defaults to moderate."""
    return _STYLE_CONTRACTS.get(level, _STYLE_CONTRACTS[_DEFAULT_LEVEL])
