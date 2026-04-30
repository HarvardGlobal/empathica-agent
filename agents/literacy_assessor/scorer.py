# Literacy Scorer
# Deterministic, rule-based scoring of patient messages against three health
# literacy levels: Low, Moderate, High.
#
# Algorithm (from agents/literacy_assessor/framework.md):
#   A. Vocabulary score  — wordlist match counts → normalised per-class fractions
#   B. Complexity score  — sentence length + clause markers → 0.2 / 0.5 / 0.8–1.0
#   C. Intent score      — question-stem matching → 0 or 1 flag per class
#   D. Weighted raw scores
#   E. Normalise → probabilities
#   F. Classification confidence = top_prob − second_prob
#   G. Signal quality    — word count, medical context richness
#   H. message_confidence = 0.7 × class_conf + 0.3 × signal_quality
#
# Session scoring aggregates message scores:
#   majority label, consistency, avg message confidence → final_confidence

from __future__ import annotations
import re
from collections import Counter
from dataclasses import dataclass, field

from agents.literacy_assessor.wordlist import (
    LOW_WORDS, MODERATE_WORDS, HIGH_WORDS,
    INTENT_LOW, INTENT_MODERATE, INTENT_HIGH,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEVELS: tuple[str, ...] = ("low", "moderate", "high")

# Wordlists and intent stems pre-lowercased at import time so per-message
# scoring never pays the .lower() cost on list entries.
_LOW_LOWER      = tuple(w.lower() for w in LOW_WORDS)
_MODERATE_LOWER = tuple(w.lower() for w in MODERATE_WORDS)
_HIGH_LOWER     = tuple(w.lower() for w in HIGH_WORDS)
_INTENT_LOW_LOWER      = tuple(s.lower() for s in INTENT_LOW)
_INTENT_MODERATE_LOWER = tuple(s.lower() for s in INTENT_MODERATE)
_INTENT_HIGH_LOWER     = tuple(s.lower() for s in INTENT_HIGH)

# Medication context terms for signal-quality scoring
_MEDICATION_CONTEXT: frozenset[str] = frozenset([
    "pill", "pills", "medicine", "medication", "medications",
    "drug", "drugs", "dose", "dosage", "tablet", "tablets",
    "capsule", "capsules", "injection", "inhaler", "insulin",
    "prescription", "prescribed",
])

# Clause markers for sentence complexity
_CLAUSE_PATTERN = re.compile(
    r'\b(and|but|because|although|however|therefore|whereas|while|'
    r'which|that|if|unless|since|so that|even though)\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MessageScore:
    level: str                          # one of LEVELS
    probabilities: dict[str, float]     # {"low": x, "moderate": y, "high": z}
    classification_confidence: float    # top_prob − second_prob
    signal_quality: float               # 0.0–1.0
    message_confidence: float           # 0.7 × class_conf + 0.3 × signal_quality
    vocab_counts: dict[str, int] = field(default_factory=dict)
    complexity: float = 0.0
    intent_flags: dict[str, float] = field(default_factory=dict)


@dataclass
class SessionAssessment:
    level: str                          # majority label across messages
    consistency: float                  # count_majority / total_messages
    avg_message_confidence: float
    final_confidence: float             # 0.6 × avg_msg_conf + 0.4 × consistency
    message_scores: list[MessageScore]
    is_stable: bool = False             # True when final_confidence >= 0.5


# ---------------------------------------------------------------------------
# Internal helpers  (all accept pre-lowercased text to avoid redundant calls)
# ---------------------------------------------------------------------------

def _count_matches(t_lower: str, wordlist_lower: tuple[str, ...]) -> int:
    return sum(1 for w in wordlist_lower if w in t_lower)


def _complexity_score(text: str) -> float:
    """
    < 6 words              → 0.2
    6–15 words, no clauses → 0.5
    > 15 words OR clauses  → 0.8–1.0
    """
    words = text.split()
    clause_count = len(_CLAUSE_PATTERN.findall(text))
    if len(words) < 6:
        return 0.2
    if len(words) <= 15 and clause_count == 0:
        return 0.5
    return min(0.8 + 0.05 * clause_count, 1.0)


def _intent_score(t_lower: str) -> tuple[float, float, float]:
    return (
        1.0 if any(stem in t_lower for stem in _INTENT_LOW_LOWER) else 0.0,
        1.0 if any(stem in t_lower for stem in _INTENT_MODERATE_LOWER) else 0.0,
        1.0 if any(stem in t_lower for stem in _INTENT_HIGH_LOWER) else 0.0,
    )


def _mid_complexity(complexity: float) -> float:
    """Triangular weight for moderate class: peaks at 0.5, zero at extremes."""
    return max(0.0, 1.0 - abs(complexity - 0.5) * 2)


def _signal_quality(t_lower: str, total_medical: int) -> float:
    """
    Additive richness score (capped at 1.0):
      word_count >= 4                → +0.3  (else +0.1)
      any medical term matched       → +0.3
      2+ medical terms matched       → +0.1
      medication context word found  → +0.3
    """
    word_count = len(t_lower.split())
    score = 0.3 if word_count >= 4 else 0.1
    if total_medical >= 1:
        score += 0.3
    if total_medical >= 2:
        score += 0.1
    if any(ctx in t_lower for ctx in _MEDICATION_CONTEXT):
        score += 0.3
    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_message(text: str) -> MessageScore:
    """Score a single patient message. Steps A–H of the framework algorithm."""
    text = text.strip()
    t_lower = text.lower()  # single .lower() for all helpers

    # A — Vocabulary counts
    low_count      = _count_matches(t_lower, _LOW_LOWER)
    moderate_count = _count_matches(t_lower, _MODERATE_LOWER)
    high_count     = _count_matches(t_lower, _HIGH_LOWER)

    total_vocab = low_count + moderate_count + high_count
    if total_vocab == 0:
        low_vocab = moderate_vocab = high_vocab = 1 / 3
    else:
        low_vocab      = low_count / total_vocab
        moderate_vocab = moderate_count / total_vocab
        high_vocab     = high_count / total_vocab

    # B — Complexity
    complexity = _complexity_score(text)

    # C — Intent flags
    intent_low, intent_mod, intent_high = _intent_score(t_lower)

    # D — Weighted raw scores
    # Weights: vocabulary 0.5, complexity 0.3, intent 0.2
    low_raw  = 0.5 * low_vocab      + 0.3 * (1.0 - complexity)          + 0.2 * intent_low
    mod_raw  = 0.5 * moderate_vocab + 0.3 * _mid_complexity(complexity)  + 0.2 * intent_mod
    high_raw = 0.5 * high_vocab     + 0.3 * complexity                   + 0.2 * intent_high

    # E — Normalise
    total_raw = low_raw + mod_raw + high_raw or 1.0
    probs = {
        "low":      low_raw  / total_raw,
        "moderate": mod_raw  / total_raw,
        "high":     high_raw / total_raw,
    }

    # F — Classification confidence
    sorted_probs = sorted(probs.values(), reverse=True)
    class_confidence = sorted_probs[0] - sorted_probs[1]

    # G — Signal quality
    signal_qual = _signal_quality(t_lower, low_count + moderate_count + high_count)

    # H — Message confidence
    msg_confidence = 0.7 * class_confidence + 0.3 * signal_qual

    level = max(probs, key=probs.__getitem__)

    return MessageScore(
        level=level,
        probabilities=probs,
        classification_confidence=class_confidence,
        signal_quality=signal_qual,
        message_confidence=msg_confidence,
        vocab_counts={"low": low_count, "moderate": moderate_count, "high": high_count},
        complexity=complexity,
        intent_flags={"low": intent_low, "moderate": intent_mod, "high": intent_high},
    )


def assess_session(messages: list[str]) -> SessionAssessment:
    """
    Score a list of patient messages and return a session-level assessment.

    Session algorithm:
      - majority label   = most frequent per-message label
      - consistency      = count_majority / total_messages
      - final_confidence = 0.6 × avg_message_confidence + 0.4 × consistency
      - is_stable        = final_confidence >= 0.5
    """
    if not messages:
        return SessionAssessment(
            level="moderate", consistency=0.0,
            avg_message_confidence=0.0, final_confidence=0.0,
            message_scores=[], is_stable=False,
        )

    scores = [score_message(m) for m in messages]
    labels = [s.level for s in scores]

    majority = Counter(labels).most_common(1)[0][0]
    consistency = labels.count(majority) / len(labels)
    avg_conf = sum(s.message_confidence for s in scores) / len(scores)
    final_confidence = 0.6 * avg_conf + 0.4 * consistency

    return SessionAssessment(
        level=majority,
        consistency=consistency,
        avg_message_confidence=avg_conf,
        final_confidence=final_confidence,
        message_scores=scores,
        is_stable=final_confidence >= 0.5,
    )
