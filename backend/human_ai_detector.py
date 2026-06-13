"""
Human vs AI Caller Detector

Analyzes the first 15-30 seconds of speech to determine if the caller is:
  - An AI/bot (IVR, virtual recruiter, automated system)
  - A human recruiter (route through or notify the user)

Detection signals:
  1. Speech rhythm — AI voices are unnaturally consistent
  2. Opener patterns — scripted greetings ("Hi, this is [name] calling from...")
  3. Vocabulary markers — formal/robotic phrasing
  4. Silence patterns — AI callers rarely have disfluencies
  5. OpenAI Whisper confidence on prosody features (future)
"""

import re
from dataclasses import dataclass, field

# ── Linguistic markers that strongly suggest an AI/IVR caller ────────────────

AI_OPENER_PATTERNS = [
    r"hi\s+this\s+is\s+\w+\s+(?:calling|reaching out)\s+(?:from|on behalf of)",
    r"hello\s+(?:may i|can i)\s+speak\s+(?:with|to)\s+\w+",
    r"i(?:'m| am)\s+(?:calling|reaching out)\s+(?:regarding|about|to discuss)",
    r"this\s+(?:call|conversation)\s+may\s+be\s+recorded",
    r"i(?:'m| am)\s+an?\s+(?:ai|virtual|automated|digital)\s+(?:assistant|recruiter|agent)",
    r"(?:thank you|thanks)\s+for\s+(?:taking|your)\s+(?:my call|time|this call)",
    r"i(?:'m| am)\s+(?:calling|reaching)\s+out\s+from\s+(?:our|the)\s+(?:talent|recruiting|hr)\s+team",
    r"i\s+(?:found|came across|saw)\s+your\s+(?:profile|resume|application)\s+on",
    r"you\s+(?:applied|submitted)\s+(?:for|an application)\s+(?:a\s+position|role|job)",
    r"this\s+is\s+an?\s+automated",
    r"press\s+\d+\s+(?:to|for)",
]

AI_VOCABULARY = [
    "regarding your application",
    "regarding your job application",
    "on behalf of",
    "i'd like to schedule",
    "at your earliest convenience",
    "do you have a few minutes",
    "is this a good time",
    "i'm reaching out",
    "talent acquisition",
    "position we have available",
    "compensation package",
    "touch base",
    "virtual assistant",
    "automated virtual assistant",
]

HUMAN_MARKERS = [
    r"\b(?:um|uh|er|hmm|like|you know|so)\b",   # disfluencies
    r"\b(?:hey|hi there|good morning|good afternoon)\b",
    r"how are you",
    r"\bactually\b",
    r"\bsorry\b",
]


@dataclass
class DetectionResult:
    is_ai: bool
    confidence: float          # 0.0 = definitely human, 1.0 = definitely AI
    signals: list[str] = field(default_factory=list)
    recommendation: str = ""


class HumanAIDetector:
    """
    Stateful detector — call `analyze(transcript_chunk)` as audio arrives.
    After enough signal is gathered, `result` becomes non-None.
    """

    def __init__(self, threshold: float = 0.65):
        self.threshold = threshold
        self.transcript_buffer: list[str] = []
        self.result: DetectionResult | None = None
        self._ai_score = 0.0
        self._human_score = 0.0
        self._total_words = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(self, new_text: str) -> DetectionResult | None:
        """
        Feed new transcript chunks as they arrive.
        Returns a DetectionResult once confidence is high enough,
        or after 60 words regardless.
        """
        if self.result is not None:
            return self.result   # already decided

        self.transcript_buffer.append(new_text.lower())
        full_text = " ".join(self.transcript_buffer)
        self._total_words = len(full_text.split())

        ai_signals = self._check_ai_patterns(full_text)
        human_signals = self._check_human_patterns(full_text)

        # Score on [0, 1]
        self._ai_score = min(len(ai_signals) * 0.25, 1.0)
        self._human_score = min(len(human_signals) * 0.20, 1.0)
        confidence = max(self._ai_score - self._human_score * 0.5, 0.0)

        # Decide early if very confident, or after 60 words
        if confidence >= self.threshold or self._total_words >= 60:
            is_ai = confidence >= self.threshold
            self.result = DetectionResult(
                is_ai=is_ai,
                confidence=confidence,
                signals=ai_signals if is_ai else human_signals,
                recommendation=(
                    "AI caller detected — activating AI responder."
                    if is_ai
                    else "Human caller detected — forwarding / notifying user."
                ),
            )
            return self.result

        return None   # still collecting signal

    def reset(self):
        self.transcript_buffer.clear()
        self.result = None
        self._ai_score = 0.0
        self._human_score = 0.0
        self._total_words = 0

    # ── Private helpers ───────────────────────────────────────────────────────

    def _check_ai_patterns(self, text: str) -> list[str]:
        signals = []
        for pattern in AI_OPENER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                signals.append(f"opener_pattern:{pattern[:40]}")
        for vocab in AI_VOCABULARY:
            if vocab in text:
                signals.append(f"ai_vocab:{vocab}")
        return signals

    def _check_human_patterns(self, text: str) -> list[str]:
        signals = []
        for pattern in HUMAN_MARKERS:
            if re.search(pattern, text, re.IGNORECASE):
                signals.append(f"human_marker:{pattern[:30]}")
        return signals


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    detector = HumanAIDetector()

    samples = [
        ("AI", "Hi this is Alex calling from our talent acquisition team. I'm reaching out regarding your application for the Software Engineer position we have available. Is this a good time to speak?"),
        ("HUMAN", "Hey um, hi, is this Venu? Yeah so I uh, I came across your resume and I wanted to chat about a role we're hiring for."),
    ]

    for label, text in samples:
        detector.reset()
        result = detector.analyze(text)
        if result is None:
            print(f"[{label}] → no decision yet\n")
            continue
        print(f"[{label}] → is_ai={result.is_ai}, confidence={result.confidence:.2f}")
        print(f"  Signals: {result.signals[:3]}")
        print(f"  → {result.recommendation}\n")
