"""
Tests for DeepgramSTT message handling — specifically that barge-in is driven by
real spoken WORDS, not background noise.

These feed canned Deepgram messages through the receive loop with a fake socket,
so they need no network. Run: pytest tests/test_stt.py -v
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from stt import BARGE_IN_MIN_WORDS, DeepgramSTT  # noqa: E402


class FakeDeepgramWS:
    """Async-iterable stand-in for the Deepgram websocket."""
    def __init__(self, messages):
        self._messages = [json.dumps(m) for m in messages]

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for m in self._messages:
            yield m


def _results(transcript, is_final):
    return {
        "type": "Results",
        "is_final": is_final,
        "channel": {"alternatives": [{"transcript": transcript}]},
    }


def run_loop(messages):
    finals: list[str] = []
    barge_ins = {"count": 0}
    utterance_ends = {"count": 0}

    async def on_transcript(text):
        finals.append(text)

    async def on_speech_started():
        barge_ins["count"] += 1

    async def on_utterance_end():
        utterance_ends["count"] += 1

    stt = DeepgramSTT(
        on_transcript=on_transcript,
        on_speech_started=on_speech_started,
        on_utterance_end=on_utterance_end,
    )
    stt._ws = FakeDeepgramWS(messages)
    asyncio.run(stt._receive_loop())
    return finals, barge_ins["count"], utterance_ends["count"]


# ── The core fix: noise must NOT barge in ─────────────────────────────────────

def test_single_word_interim_does_not_barge_in():
    """A one-word blip (typical of noise) must not interrupt the bot."""
    _, barge_ins, _ = run_loop([_results("uh", is_final=False)])
    assert barge_ins == 0


def test_empty_interim_does_not_barge_in():
    _, barge_ins, _ = run_loop([_results("", is_final=False)])
    assert barge_ins == 0


def test_multiword_interim_triggers_barge_in():
    """Real speech (>=2 words) interrupts the bot."""
    _, barge_ins, _ = run_loop([_results("hey can you", is_final=False)])
    assert barge_ins >= 1


def test_threshold_is_two_words():
    assert BARGE_IN_MIN_WORDS == 2


# ── Finals accumulate; utterance-end fires ────────────────────────────────────

def test_final_results_go_to_transcript_not_barge_in():
    finals, barge_ins, _ = run_loop([_results("hey can you brief me", is_final=True)])
    assert finals == ["hey can you brief me"]
    assert barge_ins == 0          # finals never count as barge-in


def test_utterance_end_fires_callback():
    _, _, ends = run_loop([{"type": "UtteranceEnd"}])
    assert ends == 1


def test_realistic_sequence():
    """Noise blip, then real speech, then a final, then end-of-turn."""
    finals, barge_ins, ends = run_loop([
        _results("mm", is_final=False),                 # noise -> ignored
        _results("hey can you", is_final=False),        # real speech -> barge-in
        _results("hey can you brief me", is_final=True),  # final -> accumulate
        {"type": "UtteranceEnd"},                       # turn over
    ])
    assert finals == ["hey can you brief me"]
    assert barge_ins >= 1
    assert ends == 1
