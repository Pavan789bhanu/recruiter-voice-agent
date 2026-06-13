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
    "&model=nova-2"
    "&language=en-US"
    "&punctuate=true"
    "&endpointing=500"          # 500ms silence = end of utterance
    "&interim_results=false"    # only finals
    "&smart_format=true"
)


class DeepgramSTT:
    """
    Wraps a Deepgram WebSocket connection for a single call.

    Usage:
        async with DeepgramSTT(on_transcript=my_callback) as stt:
            stt.send_audio(mulaw_bytes)
    """

    def __init__(self, on_transcript):
        """
        on_transcript: async callable(text: str) called when a final
                       transcript is available.
        """
        self.on_transcript = on_transcript
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
                if data.get("type") == "Results":
                    alternatives = (
                        data.get("channel", {})
                        .get("alternatives", [{}])
                    )
                    transcript = alternatives[0].get("transcript", "").strip()
                    is_final = data.get("is_final", False)
                    if transcript and is_final:
                        logger.debug(f"Transcript: {transcript}")
                        await self.on_transcript(transcript)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Deepgram receive error: {e}")
