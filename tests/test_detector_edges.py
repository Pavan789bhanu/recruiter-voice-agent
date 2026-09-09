"""
Edge-case tests for HumanAIDetector — focused on the classification bug that
caused live calls to be wrongly forwarded to a human and disconnected.

Run: pytest tests/test_detector_edges.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from human_ai_detector import HumanAIDetector


# ── The regression: "no AI signal" must NOT mean "human" ──────────────────────

def test_no_signal_long_speech_defaults_to_ai_not_forward():
    """
    Real-world bug: a recruiter said 60+ words that matched no AI-opener regex,
    so confidence was 0.00 and the old code forced a 'human' decision and
    forwarded/hung up the call. With no strong signal either way we must default
    to letting the AI agent handle it (is_ai=True), never forward.
    """
    d = HumanAIDetector(threshold=0.65)
    text = (
        "So this is Raquel I'm just calling you regarding the machine learning "
        "engineering position yeah it's basically a junior position with a company "
        "and they are looking for someone who has good experience working with "
        "these models and all these things so can you brief me about yourself so "
        "that I can get a clear picture about your background and experience please"
    )
    assert len(text.split()) >= 60
    result = d.analyze(text)
    assert result is not None
    assert result.is_ai is True            # AI handles — does NOT forward
    forwards = result is not None and not result.is_ai
    assert forwards is False


def test_clear_ai_opener_classified_ai():
    d = HumanAIDetector(threshold=0.65)
    result = d.analyze(
        "Hi this is Alex calling on behalf of our talent acquisition team. "
        "I'm reaching out regarding your application. Is this a good time?"
    )
    assert result is not None
    assert result.is_ai is True
    assert result.confidence >= 0.65


def test_explicit_automated_assistant_is_ai():
    d = HumanAIDetector(threshold=0.65)
    result = d.analyze(
        "Hello, this is an automated virtual assistant. Thank you for your time."
    )
    assert result is not None
    assert result.is_ai is True


def test_human_requires_positive_evidence():
    """A 'human' decision must be backed by actual human markers, not absence."""
    d = HumanAIDetector(threshold=0.5)
    # Lots of disfluencies / human markers, short of 60 words.
    text = (
        "hey um sorry, like, you know, actually how are you, uh hi there, "
        "um so yeah you know like"
    )
    result = d.analyze(text)
    if result is not None and not result.is_ai:
        assert len(result.signals) > 0       # decision backed by real signals


def test_short_input_keeps_listening():
    d = HumanAIDetector(threshold=0.65)
    assert d.analyze("Hello?") is None        # not enough to decide


def test_decision_is_sticky():
    d = HumanAIDetector(threshold=0.65)
    first = d.analyze(
        "Hi this is Alex calling on behalf of our recruiting team regarding "
        "your application. Is this a good time to talk?"
    )
    assert first is not None
    again = d.analyze("um yeah hi sorry how are you actually you know")
    assert again is first                     # locked in, won't flip


def test_confidence_bounds_and_flag_consistency():
    d = HumanAIDetector(threshold=0.65)
    result = d.analyze(
        "Hi this is Sam calling on behalf of the talent team regarding your "
        "application, is this a good time, I'd like to schedule a chat."
    )
    assert result is not None
    assert 0.0 <= result.confidence <= 1.0
    if result.is_ai:
        assert result.confidence >= 0.65


def test_reset_allows_reclassification():
    d = HumanAIDetector()
    d.analyze(
        "Hi this is Alex calling on behalf of our talent acquisition team. "
        "I'm reaching out regarding your application. Is this a good time?"
    )
    assert d.result is not None
    d.reset()
    assert d.result is None
    assert d._total_words == 0
