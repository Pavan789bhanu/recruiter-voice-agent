"""
Speech-to-Text — Deepgram real-time WebSocket transcription.

Deepgram is used because:
  - Supports streaming audio (WebSocket) with <300ms latency
  - Excellent accuracy on phone-quality audio (mulaw 8kHz from Twilio)
  - Endpoint detection (knows when speaker has finished a sentence)
"""

import asyncio
import json
import logging

import websockets

from config import DEEPGRAM_API_KEY

logger = logging.getLogger(__name__)

DEEPGRAM_WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw"
    "&sample_rate=8000"
    "&channels=1"
    "&model=nova-2-phonecall"   # tuned for 8kHz telephony audio (better accuracy)
    "&language=en-US"
    "&punctuate=true"
    "&endpointing=500"          # ms of silence before a final is emitted
    "&interim_results=true"     # needed for word-based barge-in + utterance_end_ms
    "&utterance_end_ms=1800"    # 1.8s gap = caller has truly finished (room for slow, fragmented speech)
    "&smart_format=true"
)

# Barge-in must be triggered by the caller actually SPEAKING WORDS, not by raw
# sound energy (VAD). Background noise / coughs rarely transcribe to multiple
# coherent words, so requiring >=2 words filters them out and stops the bot from
# cutting itself off mid-answer on noise.
BARGE_IN_MIN_WORDS = 2


class DeepgramSTT:
    """
    Wraps a Deepgram WebSocket connection for a single call.

    Usage:
        async with DeepgramSTT(on_transcript=my_callback) as stt:
            stt.send_audio(mulaw_bytes)
    """

    def __init__(self, on_transcript, on_speech_started=None, on_utterance_end=None):
        """
        on_transcript:     async callable(text: str) called for each final
                           transcript fragment (accumulate these).
        on_speech_started: async callable() called when the caller is genuinely
                           speaking WORDS (>=2 in an interim result) — used for
                           barge-in. This deliberately ignores mere sound energy
                           so background noise doesn't interrupt the bot.
        on_utterance_end:  async callable() called when the caller has truly
                           finished their turn (a sustained pause). Respond here.
        """
        self.on_transcript = on_transcript
        self.on_speech_started = on_speech_started
        self.on_utterance_end = on_utterance_end
        self._ws = None
        self._recv_task = None

    async def __aenter__(self):
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
        self._ws = await websockets.connect(DEEPGRAM_WS_URL, extra_headers=headers)
        self._recv_task = asyncio.create_task(self._receive_loop())
        logger.info("Deepgram STT connected")
        return self

    async def __aexit__(self, *args):
        if self._ws:
            await self._ws.send(json.dumps({"type": "CloseStream"}))
            await self._ws.close()
        if self._recv_task:
            self._recv_task.cancel()
        logger.info("Deepgram STT disconnected")

    async def send_audio(self, audio_bytes: bytes):
        """Send raw mulaw audio bytes to Deepgram."""
        if self._ws and not self._ws.closed:
            try:
                await self._ws.send(audio_bytes)
            except websockets.ConnectionClosed:
                logger.warning("Deepgram WS closed during send")

    async def _receive_loop(self):
        """Background loop that reads transcripts from Deepgram."""
        if self._ws is None:
            return
        try:
            async for message in self._ws:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "UtteranceEnd":
                    # Sustained pause — the caller has finished their turn.
                    if self.on_utterance_end is not None:
                        await self.on_utterance_end()
                    continue

                if msg_type == "Results":
                    alternatives = (
                        data.get("channel", {})
                        .get("alternatives", [{}])
                    )
                    transcript = alternatives[0].get("transcript", "").strip()
                    if not transcript:
                        continue
                    is_final = data.get("is_final", False)
                    if is_final:
                        logger.debug(f"Transcript: {transcript}")
                        await self.on_transcript(transcript)
                    elif (
                        self.on_speech_started is not None
                        and len(transcript.split()) >= BARGE_IN_MIN_WORDS
                    ):
                        # Interim result with real words → genuine speech, not noise.
                        # Trigger barge-in. (Noise rarely yields >=2 coherent words.)
                        await self.on_speech_started()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")
