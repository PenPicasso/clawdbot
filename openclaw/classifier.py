"""Task classifier — three-tier (simple/medium/complex) based on message content."""

from typing import Literal

SIMPLE_PATTERNS = {
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay",
    "yes", "no", "sure", "good morning", "good night", "good day",
}

COMPLEX_KEYWORDS = {
    "research", "analyze", "analysis", "analyse", "compare", "comparison",
    "evaluate", "evaluation", "comprehensive", "investigate", "pros and cons",
    "advantages and disadvantages", "step by step", "step-by-step",
    "elaborate", "in depth", "in-depth", "detailed report", "thorough",
    "thoroughly", "critique", "breakdown", "break down", "explain in detail",
    "full explanation", "deep dive", "deep analysis",
}


def classify(text: str) -> Literal["simple", "medium", "complex"]:
    """Classify message as simple/medium/complex based on keywords and length."""
    lowered = text.lower().strip()
    words = lowered.split()

    # Simple: very short with no complex trigger
    if len(words) <= 8 and not any(kw in lowered for kw in COMPLEX_KEYWORDS):
        # Check if it's a greeting/ack pattern
        if any(lowered.startswith(p) for p in SIMPLE_PATTERNS) or len(words) <= 3:
            return "simple"

    # Complex: contains complex keywords OR very long (150+ words)
    if any(kw in lowered for kw in COMPLEX_KEYWORDS) or len(words) > 150:
        return "complex"

    # Everything else: medium
    return "medium"
