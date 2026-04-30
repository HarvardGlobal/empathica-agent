# Tests for agents/literacy_assessor/scorer.py
#
# Coverage:
#   1. Low-literacy examples from the framework document → classified as "low"
#   2. Moderate-literacy examples                        → classified as "moderate"
#   3. High-literacy examples                            → classified as "high"
#   4. Guardrail: misused technical term                 → should NOT confidently classify as "high"
#   5. Guardrail: ambiguous / empty messages             → fallback behaviour
#   6. Scoring internals (probabilities sum to 1, confidence in range, etc.)
#   7. Session assessment (majority label, consistency, stability flag)
#   8. Full example from the framework document (3-message session)

import sys
import os
import pytest

# Allow imports from project root regardless of how pytest is invoked
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.literacy_assessor.scorer import score_message, assess_session, MessageScore, SessionAssessment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_level(text: str, expected: str, msg: str = "") -> MessageScore:
    result = score_message(text)
    label = f"[{text!r}]" + (f" — {msg}" if msg else "")
    assert result.level == expected, (
        f"{label}\n  expected={expected!r}, got={result.level!r}\n  probs={result.probabilities}"
    )
    return result


# ---------------------------------------------------------------------------
# 1. Low-literacy — verbatim examples from the framework
# ---------------------------------------------------------------------------

class TestLowLiteracy:
    @pytest.mark.parametrize("text", [
        "What is this medicine for?",
        "Why do I take this pill?",
        "Is this pill for pain?",
        "Will this make me feel better?",
        "Can I stop taking it if I feel okay?",
        "Does it hurt my stomach?",
        "Will it make me sleepy?",
        "Why do I have to take it every day?",
        "What does side effect mean?",
        "Is it okay to take this with food?",
        "What happens if I miss a dose?",
        "Can I split my pill in half?",
        "Will it make me throw up?",
        "Is there a cheaper pill?",
        "Why do I need so many pills?",
        "What's this pill for?",
        "Is it safe?",
        "Will this hurt me?",
        "What's a bad reaction?",
        "How do I take my pills?",
        "How many times a day?",
        "Help me understand.",
        "Explain it easy.",
        "Just tell me the main thing.",
        "I'm confused.",
        "Doctor said it's for my heart.",
        "I feel sick.",
        "I feel dizzy.",
        "It makes my heart race.",
        "I can't sleep.",
        "I can't poop.",
        "I have to pee all the time.",
        "My skin is itchy.",
        "I'm throwing up.",
        "Can I stop taking it?",
        "What happens if I miss one?",
        "Too expensive.",
        "What happens if I miss a pill?",
    ])
    def test_framework_low_examples(self, text: str):
        assert_level(text, "low")

    def test_plain_symptom_language(self):
        assert_level("I feel bad and weird, it hurts my stomach", "low")

    def test_cost_concern(self):
        assert_level("Is there a cheaper pill I can take instead?", "low")

    def test_trust_concern(self):
        assert_level("My neighbor said this pill is bad for me.", "low")

    def test_morning_night(self):
        assert_level("Does twice a day mean morning and night?", "low")


# ---------------------------------------------------------------------------
# 2. Moderate-literacy — verbatim examples from the framework
# ---------------------------------------------------------------------------

class TestModerateLiteracy:
    @pytest.mark.parametrize("text", [
        "What are common side effects of this drug?",
        "Can I take it with breakfast or food?",
        "Is it safe with my allergy medicine?",
        "How does it work?",
        "How long before it starts working?",
        "What should I do if I get a rash?",
        "Can I take ibuprofen with my other pills?",
        "Can I exercise while taking this medication?",
        "What happens if I feel tired after taking it?",
        "How do I know if the medicine is working?",
        "Can antibiotics upset my stomach?",
        "Should I stop suddenly?",
        "Do I need extra blood tests for this medicine?",
        "Can I take it while pregnant or breastfeeding?",
        "Am I using my inhaler correctly?",
        "Pharmacist said it might interact with my other medication.",
        "Safe to combine with alcohol?",
        "Can I take Tylenol with this?",
        "Does this interact with grapefruit?",
        "What should I do if I miss a dose?",
        "What if I'm breastfeeding?",
        "When should I stop taking it?",
        "Do I need to taper off this medication?",
        "What are the side effects?",
        "What are the serious side effects?",
        "What are the risks?",
        "How should I take this?",
        "Should I take it in the morning or night?",
        "Do I need to finish the whole bottle?",
        "Is it safe with other medicines?",
        "Can I take Advil with this?",
    ])
    def test_framework_moderate_examples(self, text: str):
        assert_level(text, "moderate")

    def test_condition_awareness(self):
        assert_level("I have diabetes — is this antibiotic safe to take?", "moderate")

    def test_practical_timing(self):
        assert_level("Should I take this medication in the morning or at night?", "moderate")

    def test_supplement_question(self):
        assert_level("Is it safe with my herbal supplements and vitamins?", "moderate")

    def test_driving_question(self):
        assert_level("Can I drive while taking this medication?", "moderate")


# ---------------------------------------------------------------------------
# 3. High-literacy — verbatim examples from the framework
# ---------------------------------------------------------------------------

class TestHighLiteracy:
    @pytest.mark.parametrize("text", [
        "What is the mechanism of action of this medication?",
        "Are there contraindications for renal impairment?",
        "Could this prolong my QT interval?",
        "What are the potential drug-drug interactions, especially with SSRIs?",
        "Is the dosage titration protocol FDA-based?",
        "How does hepatic metabolism affect efficacy?",
        "What adverse effects were reported in clinical trials?",
        "Is there evidence for off-label use?",
        "What are the pharmacokinetics in geriatric patients?",
        "Should I monitor for toxicity symptoms like hyponatremia?",
        "Is there a safer alternative in this drug class?",
        "Would titrating the dosage down reduce risk?",
        "Are there known interactions with antihypertensives?",
        "Is this medication recommended for refractory cases?",
        "What should I do if I experience serotonin syndrome symptoms?",
        "What is the bioavailability?",
        "What is the half-life?",
        "How does this drug interact with the CYP450 pathway?",
        "How does it affect hepatic gluconeogenesis?",
        "What is the dosage titration schedule?",
        "What do the evidence-based guidelines say?",
        "What did the Phase 3 clinical trial data show?",
        "Is this prescribed off-label?",
        "What are the pharmacokinetics and adverse effects of ibuprofen in patients with CKD?",
        "How does metformin affect hepatic gluconeogenesis?",
    ])
    def test_framework_high_examples(self, text: str):
        assert_level(text, "high")

    def test_drug_class_knowledge(self):
        assert_level("Is there a biguanide with fewer gastrointestinal adverse effects?", "high")

    def test_multi_clause_analytical(self):
        result = assert_level(
            "Given that the patient has renal impairment, what are the pharmacokinetics "
            "of metformin and are there contraindications I should consider?",
            "high",
        )
        # Complex, multi-clause query → should have non-trivial complexity score
        assert result.complexity >= 0.5

    def test_ssri_interaction(self):
        assert_level("What are the potential drug-drug interactions with SSRIs and this SNRI?", "high")

    def test_fda_evidence(self):
        assert_level("Is this FDA approved, or is it off-label for this indication?", "high")


# ---------------------------------------------------------------------------
# 4. Guardrails
# ---------------------------------------------------------------------------

class TestGuardrails:
    def test_misused_technical_term_not_confidently_high(self):
        """
        Framework rule: if technical terms are used incorrectly, treat as Moderate.
        We can't fully automate this rule deterministically, but we can assert that
        the classification confidence is lower than for a correctly-used technical term.
        """
        correctly_used = score_message(
            "What are the pharmacokinetics and contraindications of metformin in renal impairment?"
        )
        misused = score_message(
            "I took the pharmacokinetics pill and my QT thing went weird."
        )
        # Correctly-used technical query should have higher confidence
        assert correctly_used.message_confidence > misused.message_confidence

    def test_empty_message_returns_moderate(self):
        """Empty session should fall back to moderate."""
        result = assess_session([])
        assert result.level == "moderate"
        assert result.is_stable is False

    def test_blank_message_does_not_crash(self):
        result = score_message("")
        assert result.level in {"low", "moderate", "high"}

    def test_whitespace_only_message(self):
        result = score_message("   ")
        assert result.level in {"low", "moderate", "high"}

    def test_ambiguous_message_defaults_toward_moderate(self):
        """Very short, non-medical message — no wordlist matches — should not be high."""
        result = score_message("Okay thanks.")
        assert result.level in {"low", "moderate"}

    def test_single_technical_word_not_enough_for_high_confidence(self):
        """A lone technical term in an otherwise empty message should be low-confidence."""
        result = score_message("Contraindications?")
        # Classification may be high but confidence should be modest
        # (only 1 signal, very short message)
        assert result.message_confidence < 0.9


# ---------------------------------------------------------------------------
# 5. Scoring invariants
# ---------------------------------------------------------------------------

class TestScoringInvariants:
    SAMPLE_MESSAGES = [
        "What is this pill for?",
        "What are the side effects of this antibiotic?",
        "What is the mechanism of action of metformin?",
        "Is it safe with food?",
        "What are the pharmacokinetics in patients with renal impairment?",
    ]

    @pytest.mark.parametrize("text", SAMPLE_MESSAGES)
    def test_probabilities_sum_to_one(self, text: str):
        result = score_message(text)
        total = sum(result.probabilities.values())
        assert abs(total - 1.0) < 1e-6, f"Probs don't sum to 1: {result.probabilities}"

    @pytest.mark.parametrize("text", SAMPLE_MESSAGES)
    def test_confidence_in_range(self, text: str):
        result = score_message(text)
        assert 0.0 <= result.classification_confidence <= 1.0
        assert 0.0 <= result.signal_quality <= 1.0
        assert 0.0 <= result.message_confidence <= 1.0

    @pytest.mark.parametrize("text", SAMPLE_MESSAGES)
    def test_level_is_argmax_of_probabilities(self, text: str):
        result = score_message(text)
        expected = max(result.probabilities, key=result.probabilities.__getitem__)
        assert result.level == expected

    @pytest.mark.parametrize("text", SAMPLE_MESSAGES)
    def test_all_three_levels_present_in_probs(self, text: str):
        result = score_message(text)
        assert set(result.probabilities.keys()) == {"low", "moderate", "high"}

    @pytest.mark.parametrize("text", SAMPLE_MESSAGES)
    def test_diagnostic_fields_populated(self, text: str):
        result = score_message(text)
        assert set(result.vocab_counts.keys()) == {"low", "moderate", "high"}
        assert set(result.intent_flags.keys()) == {"low", "moderate", "high"}
        assert 0.0 <= result.complexity <= 1.0


# ---------------------------------------------------------------------------
# 6. Complexity scoring
# ---------------------------------------------------------------------------

class TestComplexityScore:
    def test_very_short_is_low_complexity(self):
        result = score_message("Pill?")
        assert result.complexity == 0.2

    def test_medium_sentence_mid_complexity(self):
        result = score_message("What are the side effects of this antibiotic?")
        assert result.complexity == 0.5

    def test_long_multi_clause_is_high_complexity(self):
        result = score_message(
            "What are the pharmacokinetics of metformin and are there contraindications "
            "for patients with hepatic impairment who are also taking SSRIs?"
        )
        assert result.complexity >= 0.8


# ---------------------------------------------------------------------------
# 7. Session assessment
# ---------------------------------------------------------------------------

class TestSessionAssessment:
    def test_all_low_session(self):
        messages = [
            "What is this pill for?",
            "Will it hurt my stomach?",
            "What are the side effects?",  # could be borderline
            "Can I stop taking it?",
            "Is it safe?",
        ]
        result = assess_session(messages)
        assert result.level == "low"
        assert result.consistency > 0.5

    def test_all_high_session(self):
        messages = [
            "What is the mechanism of action?",
            "Are there contraindications for renal impairment?",
            "What are the pharmacokinetics of metformin in geriatric patients?",
        ]
        result = assess_session(messages)
        assert result.level == "high"

    def test_consistency_is_fraction(self):
        messages = [
            "What is this pill for?",
            "What is the mechanism of action?",
            "Will it hurt my stomach?",
        ]
        result = assess_session(messages)
        assert 0.0 <= result.consistency <= 1.0

    def test_final_confidence_in_range(self):
        messages = ["What is this pill for?", "Is it safe?", "Will it make me sleepy?"]
        result = assess_session(messages)
        assert 0.0 <= result.final_confidence <= 1.0

    def test_single_message_consistency_is_one(self):
        result = assess_session(["What is this pill for?"])
        assert result.consistency == 1.0

    def test_message_scores_length_matches_input(self):
        messages = ["Pill?", "What are the side effects?", "What is the mechanism of action?"]
        result = assess_session(messages)
        assert len(result.message_scores) == len(messages)

    def test_stable_flag_set_when_confident(self):
        """Three clear high-literacy messages should produce a stable session."""
        messages = [
            "What is the mechanism of action?",
            "Are there contraindications for renal impairment?",
            "What are the pharmacokinetics in geriatric patients?",
        ]
        result = assess_session(messages)
        assert result.is_stable is True

    def test_not_stable_with_one_short_ambiguous_message(self):
        result = assess_session(["Okay."])
        assert result.is_stable is False


# ---------------------------------------------------------------------------
# 8. Full framework example (verbatim from design document)
# ---------------------------------------------------------------------------

class TestFrameworkExample:
    """
    Framework worked example:
      Msg 1: "What is this pill for?"   → low
      Msg 2: "Will it hurt my stomach?" → low
      Msg 3: "What are the side effects?" → moderate (borderline)

    Expected: majority = low, consistency ≥ 0.67
    """

    def test_example_session_majority_label(self):
        messages = [
            "What is this pill for?",
            "Will it hurt my stomach?",
            "What are the side effects?",
        ]
        result = assess_session(messages)
        assert result.level in {"low", "moderate"}  # two low, one borderline moderate
        assert result.consistency >= 2 / 3 - 1e-6

    def test_example_individual_messages(self):
        assert_level("What is this pill for?", "low", "framework example msg 1")
        assert_level("Will it hurt my stomach?", "low", "framework example msg 2")
