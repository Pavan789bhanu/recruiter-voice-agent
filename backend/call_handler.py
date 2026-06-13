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

from fastapi import WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from ai_engine import close_session, get_or_create_session
from config import AI_CONFIDENCE_THRESHOLD, FORWARD_TO_NUMBER, PUBLIC_URL
from human_ai_detector import HumanAIDetector
from notifications import send_push_notification
from stt import DeepgramSTT
from tts import synthesize_speech

logger = logging.getLogger(__name__)

AUDIO_DIR = "/tmp/ai_recruiter_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)


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
    stream = Stream(url=f"{PUBLIC_URL}/ws/media/{call_sid}")
    stream.parameter(name="track", value="inbound_track")
    connect.append(stream)
    response.append(connect)

    return str(response)


def twiml_play_audio(audio_url: str) -> str:
    """TwiML to play synthesized audio back to caller."""
    response = VoiceResponse()
    response.play(audio_url)
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

    async def run(self):
        """Main loop — reads audio frames from Twilio Media Streams."""
        logger.info(f"[{self.call_sid}] Media stream connected")

        async with DeepgramSTT(on_transcript=self._on_transcript) as stt:
            try:
                # Send greeting via TTS before caller speaks
                await self._play_greeting()

                async for raw in self.ws.iter_text():
                    msg = json.loads(raw)
                    event = msg.get("event")

                    if event == "connected":
                        logger.debug(f"[{self.call_sid}] Stream connected")

                    elif event == "start":
                        self.stream_sid = msg["start"]["streamSid"]
                        logger.info(f"[{self.call_sid}] Stream started: {self.stream_sid}")

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
                transcript = close_session(self.call_sid)
                await self._save_transcript(transcript)
                logger.info(f"[{self.call_sid}] Call ended. Turns: {self.session.turn_count}")

    # ── Transcript callback (called by Deepgram on each utterance) ────────────

    async def _on_transcript(self, text: str):
        """Called when Deepgram returns a final transcript."""
        logger.info(f"[{self.call_sid}] Heard: {text}")

        # Broadcast to iOS app via WebSocket push (connected clients)
        await self._broadcast_transcript("recruiter", text)

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
                    await self._handle_human_caller()
                    return

        # Step 2: If AI caller (or still classifying), generate AI response
        if self.caller_type != "human" and self.ai_active:
            await self._generate_and_play(text)

    # ── Response generation ────────────────────────────────────────────────────

    async def _generate_and_play(self, recruiter_text: str):
        async with self._response_lock:
            self.session.add_recruiter(recruiter_text)
            response_text = self.session.generate_response()
            logger.info(f"[{self.call_sid}] Responding: {response_text[:80]}...")

            await self._broadcast_transcript("candidate", response_text)
            await self._play_text(response_text)

    async def _play_greeting(self):
        greeting = self.session.greeting()
        await self._broadcast_transcript("candidate", greeting)
        await self._play_text(greeting)

    async def _play_text(self, text: str):
        """Synthesize text and send audio back via Twilio."""
        try:
            audio_bytes = await synthesize_speech(text)
            # Save to file and use Twilio's REST API to play it
            filename = f"{self.call_sid}_{self.session.turn_count}.mp3"
            filepath = os.path.join(AUDIO_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(audio_bytes)

            audio_url = f"{PUBLIC_URL}/audio/{filename}"
            await _twilio_play(self.call_sid, audio_url)
        except Exception as e:
            logger.error(f"[{self.call_sid}] TTS/play error: {e}")

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
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            .calls(call_sid)
            .update(twiml=twiml_play_audio(audio_url))
    )


async def _twilio_redirect(call_sid: str, to_number: str):
    """Redirect call to user's real phone number."""
    import asyncio

    from twilio.rest import Client

    from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            .calls(call_sid)
            .update(twiml=twiml_forward_to_human(to_number))
    )
