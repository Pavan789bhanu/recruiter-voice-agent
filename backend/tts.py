"""
Text-to-Speech — ElevenLabs for natural voice synthesis.

ElevenLabs is used because:
  - Most human-sounding TTS available (undetectable from real voice)
  - Streaming API — first audio chunk in ~200ms
  - Can clone your voice (optional, for maximum authenticity)
"""

import logging

import httpx

from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


async def synthesize_speech(text: str) -> bytes:
    """
    Convert text → MP3 audio bytes using ElevenLabs.
    Returns raw MP3 bytes ready to stream to caller.
    """
    url = f"{ELEVENLABS_BASE}/text-to-speech/{ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        audio_bytes = response.content
        logger.debug(f"TTS synthesized {len(text)} chars → {len(audio_bytes)} bytes")
        return audio_bytes
