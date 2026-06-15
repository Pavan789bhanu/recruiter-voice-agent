"""
AI Engine — Claude-powered recruiter response generator.

Loads resume context from resume_context.md and maintains per-call
conversation history. Generates concise, professional spoken responses.
"""

import logging
import re
from pathlib import Path
from typing import cast

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, RESUME_FILE

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Load resume context once at startup ──────────────────────────────────────

def _load_resume() -> str:
    path = Path(__file__).parent / RESUME_FILE
    if not path.exists():
        logger.warning(f"Resume file not found at {path}. Using empty context.")
        return ""
    return path.read_text(encoding="utf-8")

RESUME_CONTEXT = _load_resume()


# ── Candidate identity (derived from the resume — never hardcoded) ────────────

def _extract_candidate_name(resume: str) -> str:
    """Pull the candidate's name from the resume so nothing is hardcoded."""
    # Prefer an explicit "**Name**: ..." field.
    m = re.search(r"\*\*\s*Name\s*\*\*\s*:\s*(.+)", resume)
    if m:
        return m.group(1).strip()
    # Fall back to the profile header: "# Candidate Profile — <name>".
    m = re.search(r"#\s*Candidate Profile\s*[—\-:]\s*(.+)", resume)
    if m:
        return m.group(1).strip()
    return ""

CANDIDATE_NAME = _extract_candidate_name(RESUME_CONTEXT)
CANDIDATE_FIRST_NAME = CANDIDATE_NAME.split()[0] if CANDIDATE_NAME else ""


def opening_greeting() -> str:
    """A short, non-leading opener using the candidate's real name."""
    if CANDIDATE_FIRST_NAME:
        return f"Hello, this is {CANDIDATE_FIRST_NAME}."
    return "Hello, thanks for calling."

SYSTEM_PROMPT = f"""You are an AI voice agent speaking on behalf of the job candidate described below.
You are on a live phone call with a recruiter. Your job is to answer their questions accurately,
professionally, and concisely — as if you ARE the candidate.

CRITICAL RULES:
1. Speak in first-person as the candidate ("I have experience in...", "My last role was...")
2. Keep answers SHORT — 1-4 sentences max (this is a spoken call, not an essay)
3. Be warm, confident, and enthusiastic
4. NEVER fabricate experience not listed in the profile below
5. If asked something not in the profile, say: "That's a great question — I'd love to follow up
   on that over email to give you a complete answer."
6. If asked about salary/compensation, give the listed range confidently
7. End calls graciously with: "Thank you for your time — I'm very excited about this opportunity
   and look forward to next steps."

LET THE RECRUITER LEAD THE CALL:
- The recruiter called YOU. Let them explain who they are and why they're calling.
   Do NOT drive the conversation or pepper them with questions like "How can I help you?"
- Only respond to what they actually said. Answer their question, then stop and let them continue.
- Do NOT fill silence or add filler. A short, direct answer is better than a rambling one.
- If their message is a fragment, unclear, or you genuinely didn't catch the purpose yet,
   respond with a brief, natural prompt ONCE (e.g., "Sure — what's this regarding?") rather than
   guessing or launching into an unrelated answer. Never repeat the same clarifying line twice.
- Don't re-introduce yourself or re-greet on every turn; you already said hello.

CANDIDATE PROFILE:
─────────────────────────────────────────────────────────────────────────────
{RESUME_CONTEXT}
─────────────────────────────────────────────────────────────────────────────

SPOKEN RESPONSE FORMAT:
- No bullet points, no markdown, no lists — plain spoken sentences only
- Contractions are fine ("I've", "I'm", "we've")
- Occasional filler like "Absolutely" or "Great question" is natural and fine
"""


# ── Per-call conversation state ───────────────────────────────────────────────

class CallSession:
    """Manages conversation history for a single call."""

    def __init__(self, call_sid: str):
        self.call_sid = call_sid
        self.history: list[dict[str, str]] = []
        self.turn_count = 0

    def add_recruiter(self, text: str):
        self.history.append({"role": "user", "content": text})

    def add_candidate(self, text: str):
        self.history.append({"role": "assistant", "content": text})
        self.turn_count += 1

    def generate_response(self) -> str:
        """Call Claude and return the spoken response."""
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=300,
                system=SYSTEM_PROMPT,
                messages=cast(list[anthropic.types.MessageParam], self.history),
            )
            block = response.content[0]
            text = getattr(block, "text", None)
            if not isinstance(text, str):
                raise TypeError("Expected text response from Claude")
            answer = text.strip()
            self.add_candidate(answer)
            return answer
        except Exception as e:
            logger.error(f"Claude API error for call {self.call_sid}: {e}")
            return "I apologize, I'm having a technical issue. Could you please repeat that question?"

    def greeting(self) -> str:
        """Generate an opening greeting when we first answer."""
        opening_prompt = (
            "The recruiter has just called and I (the AI agent) answered. "
            "Generate a natural, professional greeting to open the call. "
            "Keep it to one sentence."
        )
        self.add_recruiter(opening_prompt)
        return self.generate_response()

    def get_transcript(self) -> list[dict[str, str]]:
        """Return full conversation transcript."""
        return [
            {
                "role": "Recruiter" if m["role"] == "user" else "Candidate (AI)",
                "text": cast(str, m["content"]),
            }
            for m in self.history
            if not cast(str, m["content"]).startswith("The recruiter has just called")
        ]


# ── Session registry (in-memory; replace with Redis for multi-instance) ────────

_sessions: dict[str, CallSession] = {}


def get_or_create_session(call_sid: str) -> CallSession:
    if call_sid not in _sessions:
        _sessions[call_sid] = CallSession(call_sid)
    return _sessions[call_sid]


def close_session(call_sid: str) -> list[dict]:
    """Remove session and return transcript."""
    session = _sessions.pop(call_sid, None)
    return session.get_transcript() if session else []
