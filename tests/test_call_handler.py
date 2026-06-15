"""
Turn-taking / conversation tests for CallOrchestrator.

Covers the bugs reported during live testing:
  - audio framing over the Twilio WebSocket
  - barge-in (caller interrupts the bot mid-sentence)
  - stale replies dropped when the caller resumes
  - backchannels ignored, fragments accumulated until UtteranceEnd
  - human-forwarding gated by config (no surprise disconnects)

These are async but driven with asyncio.run(), so they need no pytest plugin.

Run: pytest tests/test_call_handler.py -v
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import call_handler  # noqa: E402
from call_handler import CallOrchestrator  # noqa: E402
from human_ai_detector import DetectionResult  # noqa: E402


# ── Test doubles ──────────────────────────────────────────────────────────────

class FakeWS:
    """Minimal stand-in for the Twilio media-stream WebSocket."""
    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, msg: str):
        self.sent.append(json.loads(msg))


def make_orchestrator():
    orch = CallOrchestrator("CAtest123", FakeWS())
    orch.stream_sid = "MZtest"

    # Don't reach into main.py / iOS broadcast during unit tests.
    async def _noop(*a, **k):
        return None
    orch._broadcast_transcript = _noop
    orch._broadcast_event = _noop
    return orch


def events_of(orch, kind):
    return [e for e in orch.ws.sent if e.get("event") == kind]


# ── Audio framing ─────────────────────────────────────────────────────────────

def test_play_audio_frames_and_mark():
    orch = make_orchestrator()
    audio = b"\x00" * 350          # 350 bytes @ 160/frame -> 3 frames

    asyncio.run(orch._play_audio(audio))

    media = events_of(orch, "media")
    assert len(media) == 3
    assert all(e["streamSid"] == "MZtest" for e in media)
    assert len(events_of(orch, "mark")) == 1   # mark sent after audio
    assert orch._speaking is False             # flag cleared when done


def test_play_audio_without_stream_sid_is_safe():
    orch = make_orchestrator()
    orch.stream_sid = None
    asyncio.run(orch._play_audio(b"\x00" * 160))
    assert orch.ws.sent == []                  # nothing sent, no crash


def test_stop_speaking_sends_clear():
    orch = make_orchestrator()
    asyncio.run(orch._stop_speaking())
    assert len(events_of(orch, "clear")) == 1
    assert orch._speaking is False


# ── Barge-in ──────────────────────────────────────────────────────────────────

def test_barge_in_after_grace_stops_playback():
    import call_handler as ch
    orch = make_orchestrator()
    big = b"\x00" * (160 * 400)     # long audio so it's still playing

    async def scenario():
        epoch_before = orch._turn_epoch
        play = asyncio.create_task(orch._play_audio(big))
        await asyncio.sleep(0.05)
        assert orch._speaking is True
        # Simulate that playback began before the grace window (so grace has passed).
        orch._speak_start_ts -= (ch.BARGE_IN_GRACE_SEC + 0.1)
        await orch._on_speech_started()        # genuine interruption
        assert orch._speaking is False
        # Epoch must NOT change on a barge-in — only a new completed turn supersedes.
        assert orch._turn_epoch == epoch_before
        await asyncio.sleep(0.01)
        assert play.done()
        return True

    assert asyncio.run(scenario()) is True
    assert len(events_of(orch, "media")) < 400
    assert len(events_of(orch, "clear")) >= 1


def test_barge_in_within_grace_is_ignored():
    """A blip in the first moments of a reply must not cut it off."""
    orch = make_orchestrator()
    big = b"\x00" * (160 * 400)

    async def scenario():
        play = asyncio.create_task(orch._play_audio(big))
        await asyncio.sleep(0.05)
        assert orch._speaking is True
        await orch._on_speech_started()        # within grace -> ignored
        assert orch._speaking is True          # still speaking
        await orch._stop_speaking()            # cleanup
        await asyncio.sleep(0.01)
        return play.done()

    assert asyncio.run(scenario()) is True


def test_new_turn_bumps_epoch():
    orch = make_orchestrator()
    orch.session.add_candidate("greet")        # turn_count -> 1 (not first turn)

    async def fake_handle(text):
        return None
    orch._handle_utterance = fake_handle

    async def scenario():
        before = orch._turn_epoch
        orch._pending = ["please tell me about your background"]
        await orch._on_utterance_end()
        return orch._turn_epoch, before

    after, before = asyncio.run(scenario())
    assert after == before + 1                 # a real new turn supersedes


# ── Turn detection: accumulate fragments, ignore backchannels ─────────────────

def test_transcripts_accumulate_until_utterance_end():
    orch = make_orchestrator()

    async def scenario():
        await orch._on_transcript("so I'm calling")
        await orch._on_transcript("about the role")
        return list(orch._pending)

    assert asyncio.run(scenario()) == ["so I'm calling", "about the role"]


def test_empty_utterance_end_does_nothing():
    orch = make_orchestrator()
    orch._pending = []
    asyncio.run(orch._on_utterance_end())
    assert orch._handle_task is None


def test_backchannel_ignored_after_first_turn():
    orch = make_orchestrator()
    orch.session.add_candidate("Hello, this is Pavan.")   # turn_count -> 1
    orch._pending = ["yeah"]

    asyncio.run(orch._on_utterance_end())
    assert orch._pending == []            # consumed
    assert orch._handle_task is None      # but no reply triggered


# ── Stale reply handling ──────────────────────────────────────────────────────

def test_stale_reply_dropped_when_caller_resumes():
    orch = make_orchestrator()
    orch.caller_type = "ai"

    spoken: list[str] = []

    async def fake_speak(text):
        spoken.append(text)
    orch._speak = fake_speak

    def gen():
        orch._turn_epoch += 1             # simulate caller speaking again
        return "stale answer"
    orch.session.generate_response = gen

    asyncio.run(orch._generate_and_play("tell me about your background please"))
    assert spoken == []                   # stale -> not spoken


def test_fresh_reply_is_spoken():
    orch = make_orchestrator()
    orch.caller_type = "ai"

    spoken: list[str] = []

    async def fake_speak(text):
        spoken.append(text)
    orch._speak = fake_speak
    orch.session.generate_response = lambda: "Here is my background."

    asyncio.run(orch._generate_and_play("tell me about your experience"))
    assert spoken == ["Here is my background."]


# ── Human-forwarding gate ─────────────────────────────────────────────────────

def test_human_detected_but_forwarding_disabled_keeps_bot():
    orch = make_orchestrator()
    orch.detector.analyze = lambda t: DetectionResult(
        is_ai=False, confidence=0.9, signals=["human_marker"], recommendation="human"
    )
    orch.session.generate_response = lambda: "Sure, happy to help."

    forwarded = {"called": False}

    async def fake_forward():
        forwarded["called"] = True
    orch._handle_human_caller = fake_forward

    spoken: list[str] = []

    async def fake_speak(text):
        spoken.append(text)
    orch._speak = fake_speak

    prev = call_handler.ENABLE_HUMAN_FORWARDING
    call_handler.ENABLE_HUMAN_FORWARDING = False
    try:
        asyncio.run(orch._handle_utterance("hey there how are you doing today friend"))
    finally:
        call_handler.ENABLE_HUMAN_FORWARDING = prev

    assert forwarded["called"] is False   # no destructive forward
    assert orch.caller_type == "ai"       # bot takes over
    assert spoken == ["Sure, happy to help."]


def test_extract_candidate_name_is_dynamic():
    from ai_engine import _extract_candidate_name
    assert _extract_candidate_name("- **Name**: Jane Q Doe\n") == "Jane Q Doe"
    assert _extract_candidate_name("# Candidate Profile — John Smith\n") == "John Smith"
    assert _extract_candidate_name("nothing relevant here") == ""


def test_greeting_uses_resume_name_not_hardcoded():
    import ai_engine
    greeting = ai_engine.opening_greeting()
    assert isinstance(greeting, str) and greeting
    # The greeting must be derived, never the old hardcoded literal.
    if ai_engine.CANDIDATE_FIRST_NAME:
        # Resume provided a name -> it is used and matches the parsed first name.
        assert ai_engine.CANDIDATE_FIRST_NAME in greeting
        assert ai_engine.CANDIDATE_FIRST_NAME == ai_engine.CANDIDATE_NAME.split()[0]
    else:
        # No name in the resume -> neutral fallback (still not hardcoded).
        assert greeting == "Hello, thanks for calling."


def test_human_forwarded_when_enabled():
    orch = make_orchestrator()
    orch.detector.analyze = lambda t: DetectionResult(
        is_ai=False, confidence=0.9, signals=["human_marker"], recommendation="human"
    )

    forwarded = {"called": False}

    async def fake_forward():
        forwarded["called"] = True
    orch._handle_human_caller = fake_forward

    prev = call_handler.ENABLE_HUMAN_FORWARDING
    call_handler.ENABLE_HUMAN_FORWARDING = True   # FORWARD_TO_NUMBER set in conftest
    try:
        asyncio.run(orch._handle_utterance("hey there how are you doing today friend"))
    finally:
        call_handler.ENABLE_HUMAN_FORWARDING = prev

    assert forwarded["called"] is True
    assert orch.caller_type == "human"
