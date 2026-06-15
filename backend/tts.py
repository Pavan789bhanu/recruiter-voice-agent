"""
Text-to-Speech — ElevenLabs for natural voice synthesis.

ElevenLabs is used because:
  - Most human-sounding TTS available (undetectable from real voice)
  - Streaming API — first audio chunk in ~200ms
  - Can clone your voice (optional, for maximum authenticity)

Fallback: AWS Polly (cheaper, slightly more robotic)
"""

import logging

import httpx

from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


async def synthesize_speech(text: str, output_format: str = "mp3_44100_128") -> bytes:
    """
    Convert text → audio bytes using ElevenLabs.

    output_format:
      - "mp3_44100_128" (default) for file/<Play> use
      - "ulaw_8000" for Twilio Media Streams (8kHz mu-law, sent over the WS)
    """
    url = f"{ELEVENLABS_BASE}/text-to-speech/{ELEVENLABS_VOICE_ID}?output_format={output_format}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",   # lowest latency model
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            # ElevenLabs puts the real reason in the JSON body, not the status line.
            # e.g. {"detail":{"status":"detected_unusual_activity","message":"..."}}
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            logger.error(
                f"ElevenLabs TTS failed [{response.status_code}]: {detail}"
            )
            response.raise_for_status()
        audio_bytes = response.content
        logger.debug(f"TTS synthesized {len(text)} chars → {len(audio_bytes)} bytes")
        return audio_bytes


async def synthesize_to_twilio_url(text: str, call_sid: str, storage_path: str) -> str:
    """
    Synthesize speech and save to a publicly accessible URL.
    Twilio's <Play> verb needs a URL, not raw bytes.

    In production: save to S3 and return the S3 URL.
    For local dev: save to /tmp and serve via FastAPI static files.
    """
    audio = await synthesize_speech(text)

    import os
    file_path = os.path.join(storage_path, f"{call_sid}_response.mp3")
    with open(file_path, "wb") as f:
        f.write(audio)

    from config import PUBLIC_URL
    filename = os.path.basename(file_path)
    return f"{PUBLIC_URL}/audio/{filename}"


# ── AWS Polly fallback (no ElevenLabs key) ────────────────────────────────────

async def synthesize_speech_polly(text: str) -> str:
    """
    Fallback: use AWS Polly via boto3.
    Returns URL pointing to saved audio file.
    """
    try:
        import boto3
        polly = boto3.client("polly", region_name="us-east-1")
        response = polly.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId="Joanna",
            Engine="neural",
        )
        return response["AudioStream"].read()
    except Exception as e:
        logger.error(f"Polly TTS error: {e}")
        raise
