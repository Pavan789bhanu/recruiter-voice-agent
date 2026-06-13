"""
Tests for HumanAIDetector.

Run: pytest tests/test_detector.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from human_ai_detector import HumanAIDetector, DetectionResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

AI_OPENER = (
    "Hi this is Alex calling on behalf of our talent acquisition team. "
    "I'm reaching out regarding your application for the Software Engineer "
    "position we have available. Is this a good time to speak?"
)

HUMAN_OPENER = (
    "Hey um, hi, is this Pavan? Yeah so I uh, came across your profile and "
    "I wanted to have a quick chat about a role we're looking to fill."
)

EXPLICIT_AI = "Hello, this is an automated virtual assistant calling regarding your job application."

HUMAN_NATURAL = "Hey Pavan, how are you? I'm calling about a position at our company, do you have a few minutes?"


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestHumanAIDetector:

    def test_ai_opener_detected(self):
        d = HumanAIDetector(threshold=0.65)
        result = d.analyze(AI_OPENER)
        assert result is not None
        assert result.is_ai is True
        assert result.confidence >= 0.65

    def test_human_opener_detected(self):
        d = HumanAIDetector(threshold=0.65)
        result = d.analyze(HUMAN_OPENER)
        if result is not None:
            assert result.is_ai is False

    def test_explicit_ai_detected(self):
        d = HumanAIDetector(threshold=0.50)
        result = d.analyze(EXPLICIT_AI)
        assert result is not None
        assert result.is_ai is True

    def test_result_is_detection_result(self):
        d = HumanAIDetector()
        result = d.analyze(AI_OPENER)
        assert isinstance(result, DetectionResult)

    def test_result_has_signals(self):
        d = HumanAIDetector()
        result = d.analyze(AI_OPENER)
        assert result is not None
        assert len(result.signals) > 0

    def test_result_has_recommendation(self):
        d = HumanAIDetector()
        result = d.analyze(AI_OPENER)
        assert result is not None
        assert len(result.recommendation) > 0

    def test_reset_clears_state(self):
        d = HumanAIDetector()
        d.analyze(AI_OPENER)
        assert d.result is not None
        d.reset()
        assert d.result is None
        assert d._total_words == 0

    def test_no_result_on_short_text(self):
        """Short ambiguous text should not trigger a decision yet."""
        d = HumanAIDetector(threshold=0.65)
        result = d.analyze("Hello.")
        # Either None (still collecting) or low confidence
        if result is not None:
            assert result.confidence < 0.65 or result.is_ai is False

    def test_forces_decision_at_60_words(self):
        """Should always return a result after 60+ words."""
        d = HumanAIDetector(threshold=0.99)  # Very high threshold
        long_text = "Hello " * 65   # 65 words, all neutral
        result = d.analyze(long_text)
        assert result is not None  # Must decide regardless

    def test_confidence_between_0_and_1(self):
        d = HumanAIDetector()
        result = d.analyze(AI_OPENER)
        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_is_ai_flag_matches_confidence_threshold(self):
        threshold = 0.65
        d = HumanAIDetector(threshold=threshold)
        result = d.analyze(AI_OPENER)
        assert result is not None
        if result.confidence >= threshold:
            assert result.is_ai is True
        else:
            assert result.is_ai is False
