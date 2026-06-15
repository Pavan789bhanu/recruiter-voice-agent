"""
Call Handler — orchestrates the full real-time call flow.

Flow:
  1. Twilio calls /webhook/incoming  → TwiML answers & opens Media Stream
  2. Twilio streams audio frames to /ws/media/{call_sid}
  3. We pipe audio → Deepgram STT → text
  4. HumanAIDetector classifies the caller
     - AI detected  → Claude generates response → ElevenLabs TTS → play back
     - Human detected → forward call to real phone / send push notification
  5. Conversation transcript saved on call end
"""

import asyncio
import base64
import json
import logging
import os
import time

from fastapi import WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, Gather, Stream, VoiceResponse

from ai_engine import close_session, get_or_create_session, opening_greeting
from config import (
    AI_CONFIDENCE_THRESHOLD,
    ENABLE_HUMAN_FORWARDING,
    FORWARD_TO_NUMBER,
    PUBLIC_URL,
)
from human_ai_detector import HumanAIDetector
from notifications import send_push_notification
from stt import DeepgramSTT
from tts import synthesize_speech

logger = logging.getLogger(__name__)

AUDIO_DIR = "/tmp/ai_recruiter_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Don't let a brief sound (a short "mm", a cough, line noise) cut the bot off in
# the first moments of a reply — give the caller a chance to actually hear it.
BARGE_IN_GRACE_SEC = 0.8


# ── TwiML responses ───────────────────────────────────────────────────────────

def twiml_answer(call_sid: str) -> str:
    """
    TwiML to answer the call and open a Media Stream WebSocket
    so we can process audio in real-time.
    """
    response = VoiceResponse()

    # Brief pause while we spin up (feels natural)
    response.pause(length=1)

    # Open WebSocket for audio streaming
    connect = Connect()
    ws_url = PUBLIC_URL.replace("https://", "wss://").replace("http://", "ws://")
    stream = Stream(url=f"{ws_url}/ws/media/{call_sid}")
    stream.parameter(name="track", value="inbound_track")
    connect.append(stream)
    response.append(connect)

    return str(response)


def twiml_play_audio(audio_url: str) -> str:
    """TwiML to play synthesized audio back to caller."""
    response = VoiceResponse()
    response.play(audio_url)
    return str(response)


def twiml_say(text: str) -> str:
    """Fallback TwiML using Twilio's built-in TTS (no ElevenLabs needed)."""
    response = VoiceResponse()
    response.say(text, voice="Polly.Joanna-Neural")
    return str(response)


def twiml_forward_to_human(to_number: str) -> str:
    """TwiML to forward the call to the real user's phone."""
    response = VoiceResponse()
    response.say(
        "Please hold while I connect you.",
        voice="Polly.Joanna-Neural",
    )
    response.dial(to_number)
    return str(response)


def twiml_gather_fallback(call_sid: str) -> str:
    """Gather DTMF/speech when streaming isn't available."""
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"{PUBLIC_URL}/webhook/speech/{call_sid}",
        method="POST",
        timeout=5,
        speech_timeout="auto",
        language="en-US",
    )
    response.append(gather)
    return str(response)


# ── WebSocket media stream handler ────────────────────────────────────────────

class CallOrchestrator:
    """
    Manages the full lifecycle of one call's audio stream.
    Instantiated once per call WebSocket connection.
    """

    def __init__(self, call_sid: str, websocket: WebSocket):
        self.call_sid = call_sid
        self.ws = websocket
        self.detector = HumanAIDetector(threshold=AI_CONFIDENCE_THRESHOLD)
        self.session = get_or_create_session(call_sid)
        self.caller_type: str | None = None   # "ai" | "human"
        self.stream_sid: str | None = None
        self.ai_active = True   # can be toggled remotely via REST
        self._response_lock = asyncio.Lock()

        # ── Turn-taking state ─────────────────────────────────────────────────
        self._speaking = False                 # is the bot currently playing audio?
        self._speak_start_ts = 0.0             # when current playback began (monotonic)
        self._play_task: asyncio.Task | None = None   # current playback task
        self._pending: list[str] = []          # final fragments for the current turn
        self._greeting_task: asyncio.Task | None = None
        self._handle_task: asyncio.Task | None = None
        self._ack_cache: dict[str, bytes] = {}  # cached filler audio (ulaw bytes)
        self._turn_epoch = 0                   # bumped whenever the caller speaks again

    async def run(self):
        """Main loop — reads audio frames from Twilio Media Streams."""
        logger.info(f"[{self.call_sid}] Media stream connected")

        try:
            stt_cm = DeepgramSTT(
                on_transcript=self._on_transcript,
                on_speech_started=self._on_speech_started,
                on_utterance_end=self._on_utterance_end,
            )
            stt = await stt_cm.__aenter__()
        except Exception as e:
            logger.error(
                f"[{self.call_sid}] Could not connect Deepgram STT ({e}). "
                "Check DEEPGRAM_API_KEY is valid and the project has credits."
            )
            try:
                await _twilio_say(
                    self.call_sid,
                    "Sorry, we're unable to take your call right now. Please try again later.",
                )
            except Exception:
                pass
            return

        try:
            async for raw in self.ws.iter_text():
                msg = json.loads(raw)
                event = msg.get("event")

                if event == "connected":
                    logger.debug(f"[{self.call_sid}] Stream connected")

                elif event == "start":
                    self.stream_sid = msg["start"]["streamSid"]
                    logger.info(f"[{self.call_sid}] Stream started: {self.stream_sid}")
                    # Greet only now — we need streamSid to send audio back over the WS.
                    # Run it in the background so this loop keeps ingesting caller
                    # audio (enables barge-in even during the greeting).
                    self._greeting_task = asyncio.create_task(self._play_greeting())

                elif event == "media":
                    # Decode mulaw audio and send to Deepgram
                    audio_b64 = msg["media"]["payload"]
                    audio_bytes = base64.b64decode(audio_b64)
                    await stt.send_audio(audio_bytes)

                elif event == "stop":
                    logger.info(f"[{self.call_sid}] Stream stopped")
                    break

        except WebSocketDisconnect:
            logger.info(f"[{self.call_sid}] WebSocket disconnected")
        except Exception as e:
            logger.error(f"[{self.call_sid}] Error in media stream: {e}")
        finally:
            # Stop any in-flight playback / background tasks before tearing down.
            for t in (self._greeting_task, self._handle_task, self._play_task):
                if t and not t.done():
                    t.cancel()
            await stt_cm.__aexit__(None, None, None)
            transcript = close_session(self.call_sid)
            await self._save_transcript(transcript)
            logger.info(f"[{self.call_sid}] Call ended. Turns: {self.session.turn_count}")

    # ── Transcript callback (called by Deepgram on each utterance) ────────────

    async def _on_speech_started(self):
        """
        The caller started talking. If the bot is mid-sentence, stop so we don't
        talk over them — but only after a short grace period, so a brief sound
        right as a reply begins doesn't swallow the whole answer.

        Note: we do NOT mark the reply stale here. A reply is only superseded by a
        genuinely new completed turn (see _on_utterance_end); otherwise a stray
        sound during generation would silently drop a perfectly good answer.
        """
        if self._speaking:
            elapsed = time.monotonic() - self._speak_start_ts
            if elapsed < BARGE_IN_GRACE_SEC:
                return
            logger.info(f"[{self.call_sid}] Barge-in — caller interrupted, stopping playback")
            await self._stop_speaking()

    async def _on_transcript(self, text: str):
        """
        A final transcript fragment. We DON'T respond here — the caller may only
        be pausing mid-thought. We just collect fragments for the current turn
        and wait for Deepgram's UtteranceEnd to tell us they've actually finished.
        """
        logger.info(f"[{self.call_sid}] Heard: {text}")
        await self._broadcast_transcript("recruiter", text)
        self._pending.append(text)

    async def _on_utterance_end(self):
        """
        The caller has finished their turn (sustained pause). Now — and only now —
        assemble everything they said and respond to it as one complete thought.
        """
        combined = " ".join(self._pending).strip()
        self._pending = []
        if not combined:
            return

        # Ignore tiny backchannels ("yeah", "okay", "mm") — keep listening instead
        # of derailing into a reply. The very first turn is always allowed through.
        if self.session.turn_count > 0 and len(combined.split()) < 2:
            logger.info(f"[{self.call_sid}] Ignoring backchannel: {combined!r}")
            return

        # A genuinely new, completed turn supersedes anything pending: bump the
        # epoch so an in-flight reply for the previous turn is dropped.
        self._turn_epoch += 1

        # Cancel any in-flight reply AND stop its audio sender before starting a
        # new turn, so the previous response can never play over this one.
        if self._handle_task and not self._handle_task.done():
            self._handle_task.cancel()
        await self._stop_speaking()
        self._handle_task = asyncio.create_task(self._handle_utterance(combined))

    async def _handle_utterance(self, text: str):
        """Classify (first turn) then generate + speak a response."""
        # Step 1: Classify caller if not yet determined
        if self.caller_type is None:
            result = self.detector.analyze(text)
            if result is not None:
                self.caller_type = "ai" if result.is_ai else "human"
                logger.info(
                    f"[{self.call_sid}] Caller classified as: {self.caller_type} "
                    f"(confidence={result.confidence:.2f})"
                )
                await self._broadcast_event("caller_classified", {
                    "type": self.caller_type,
                    "confidence": result.confidence,
                    "signals": result.signals[:5],
                })

                if self.caller_type == "human":
                    if ENABLE_HUMAN_FORWARDING and FORWARD_TO_NUMBER:
                        await self._handle_human_caller()
                        return
                    # Forwarding disabled — don't tear down the call. Let the AI
                    # agent keep handling it instead.
                    logger.info(
                        f"[{self.call_sid}] Human detected but forwarding disabled — "
                        "AI will continue handling the call."
                    )
                    self.caller_type = "ai"

        # Step 2: If AI caller (or still classifying), generate AI response
        if self.caller_type != "human" and self.ai_active:
            await self._generate_and_play(text)

    # ── Response generation ────────────────────────────────────────────────────

    async def _generate_and_play(self, recruiter_text: str):
        async with self._response_lock:
            epoch = self._turn_epoch       # snapshot: detect if caller speaks again
            self.session.add_recruiter(recruiter_text)

            # Generate in a worker thread (the Anthropic SDK call is blocking) so
            # we can fill the wait with a short acknowledgment if it runs long.
            gen_task = asyncio.create_task(asyncio.to_thread(self.session.generate_response))
            done, _ = await asyncio.wait({gen_task}, timeout=0.6)
            if gen_task not in done and self._turn_epoch == epoch:
                # Claude is taking a moment — cover the silence with a quick filler.
                await self._speak_ack()
            response_text = await gen_task

            # If the caller started speaking again while we were thinking, this
            # reply is stale — stay quiet and let their new turn take over.
            if self._turn_epoch != epoch:
                logger.info(f"[{self.call_sid}] Caller resumed; dropping stale reply")
                return

            logger.info(f"[{self.call_sid}] Responding: {response_text[:80]}...")
            await self._broadcast_transcript("candidate", response_text)
            await self._speak(response_text)

    async def _play_greeting(self):
        # Keep the opener short and non-leading so the caller explains why they're
        # calling. Name is derived from the resume (not hardcoded).
        greeting = opening_greeting()
        self.session.add_candidate(greeting)
        await self._broadcast_transcript("candidate", greeting)
        await self._speak(greeting)

    # ── Speaking (interruptible playback) ─────────────────────────────────────

    async def _speak(self, text: str):
        """
        Synthesize `text` and play it to the caller as a cancellable task,
        so a barge-in can stop it mid-sentence.
        """
        audio = await synthesize_speech(text, output_format="ulaw_8000")
        await self._play_audio(audio)

    async def _speak_ack(self):
        """Play a short, natural filler to cover Claude's thinking time."""
        import random
        phrase = random.choice(["Mm-hm.", "Sure.", "Right, yeah.", "Of course."])
        try:
            if phrase not in self._ack_cache:
                self._ack_cache[phrase] = await synthesize_speech(
                    phrase, output_format="ulaw_8000"
                )
            await self._play_audio(self._ack_cache[phrase])
        except Exception as e:
            logger.warning(f"[{self.call_sid}] Ack playback skipped: {e}")

    async def _play_audio(self, audio: bytes):
        """
        Stream mu-law audio back to the caller as outbound Media Stream frames
        over the SAME WebSocket, as a cancellable task.

        We must NOT use Twilio REST `calls.update(twiml=...)` here: that replaces
        the running <Connect><Stream> TwiML and tears down the media stream,
        ending the call after one playback.
        """
        if not self.stream_sid:
            logger.warning(f"[{self.call_sid}] No stream_sid yet; cannot play audio")
            return

        async def _sender():
            # Chunk into ~20ms frames (160 bytes @ 8kHz mu-law) and pace them so
            # the bot's audio plays in real time — which makes barge-in responsive
            # (we stop sending the instant the caller speaks instead of having
            # already dumped the whole clip into Twilio's buffer).
            frame = 160
            for i in range(0, len(audio), frame):
                payload = base64.b64encode(audio[i:i + frame]).decode("ascii")
                await self.ws.send_text(json.dumps({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": payload},
                }))
                await asyncio.sleep(0.018)  # ~20ms per frame, slight headroom
            await self.ws.send_text(json.dumps({
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": f"turn-{self.session.turn_count}"},
            }))

        self._speaking = True
        self._speak_start_ts = time.monotonic()
        self._play_task = asyncio.create_task(_sender())
        try:
            await self._play_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[{self.call_sid}] TTS/stream error: {e}")
        finally:
            self._speaking = False

    async def _stop_speaking(self):
        """Cancel in-flight playback and flush Twilio's outbound buffer."""
        self._speaking = False
        if self._play_task and not self._play_task.done():
            self._play_task.cancel()
            try:
                await self._play_task
            except asyncio.CancelledError:
                pass
        if self.stream_sid:
            # `clear` tells Twilio to drop any audio it has buffered for playback.
            try:
                await self.ws.send_text(json.dumps({
                    "event": "clear",
                    "streamSid": self.stream_sid,
                }))
            except Exception:
                pass

    # ── Human caller handling ─────────────────────────────────────────────────

    async def _handle_human_caller(self):
        """Notify user + optionally forward the call."""
        logger.info(f"[{self.call_sid}] Forwarding to human user")
        await send_push_notification(
            title="Human Recruiter Calling",
            body="A real recruiter is on your Twilio line. Tap to listen.",
            data={"call_sid": self.call_sid},
        )
        if FORWARD_TO_NUMBER:
            await _twilio_redirect(self.call_sid, FORWARD_TO_NUMBER)

    # ── Broadcasting to iOS companion app ─────────────────────────────────────

    async def _broadcast_transcript(self, speaker: str, text: str):
        from main import broadcast_to_clients
        await broadcast_to_clients(self.call_sid, {
            "type": "transcript",
            "speaker": speaker,
            "text": text,
        })

    async def _broadcast_event(self, event: str, data: dict):
        from main import broadcast_to_clients
        await broadcast_to_clients(self.call_sid, {"type": event, **data})

    # ── Transcript persistence ─────────────────────────────────────────────────

    async def _save_transcript(self, transcript: list[dict]):
        import datetime
        import json
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"/tmp/transcripts/{self.call_sid}_{ts}.json"
        os.makedirs("/tmp/transcripts", exist_ok=True)
        with open(path, "w") as f:
            json.dump(transcript, f, indent=2)
        logger.info(f"[{self.call_sid}] Transcript saved: {path}")


# ── Twilio REST helpers ───────────────────────────────────────────────────────

async def _twilio_play(call_sid: str, audio_url: str):
    """Use Twilio REST API to inject audio into an ongoing call."""
    import asyncio

    from twilio.rest import Client

    from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            .calls(call_sid)
            .update(twiml=twiml_play_audio(audio_url))
    )


async def _twilio_say(call_sid: str, text: str):
    """Speak text into an ongoing call using Twilio's built-in TTS (ElevenLabs fallback)."""
    import asyncio

    from twilio.rest import Client

    from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            .calls(call_sid)
            .update(twiml=twiml_say(text))
    )


async def _twilio_redirect(call_sid: str, to_number: str):
    """Redirect call to user's real phone number."""
    import asyncio

    from twilio.rest import Client

    from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            .calls(call_sid)
            .update(twiml=twiml_forward_to_human(to_number))
    )
