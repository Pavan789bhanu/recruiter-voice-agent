"""
Configuration — loads from environment variables.
Copy .env.example → .env and fill in your keys.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# ── Twilio ──────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID   = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN    = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_PHONE_NUMBER  = os.environ["TWILIO_PHONE_NUMBER"]   # Your Twilio number

# ── Deepgram (real-time STT) ─────────────────────────────────────────────────
DEEPGRAM_API_KEY     = os.environ["DEEPGRAM_API_KEY"]

# ── Anthropic / Claude ───────────────────────────────────────────────────────
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]
CLAUDE_MODEL         = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

# ── ElevenLabs (TTS) ─────────────────────────────────────────────────────────
ELEVENLABS_API_KEY   = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID  = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # default: Rachel

# ── App ───────────────────────────────────────────────────────────────────────
PORT                 = int(os.environ.get("PORT", 8000))
HOST                 = os.environ.get("HOST", "0.0.0.0")
PUBLIC_URL           = os.environ["PUBLIC_URL"]  # e.g. https://yourserver.example.com

# ── Forwarding (if human detected, ring this number) ─────────────────────────
FORWARD_TO_NUMBER    = os.environ.get("FORWARD_TO_NUMBER", "")   # your real cell number

# When False, a "human" classification will NOT forward/hang up — the AI agent
# keeps handling the call. Keep this off until forwarding + push are set up and
# the detector is tuned, otherwise misclassifications will drop live calls.
ENABLE_HUMAN_FORWARDING = os.environ.get("ENABLE_HUMAN_FORWARDING", "false").lower() in ("1", "true", "yes")

# ── AI Detection thresholds ──────────────────────────────────────────────────
AI_CONFIDENCE_THRESHOLD = float(os.environ.get("AI_CONFIDENCE_THRESHOLD", "0.65"))

# ── Resume context file ───────────────────────────────────────────────────────
RESUME_FILE          = os.environ.get("RESUME_FILE", "resume_context.md")
