"""Tool router — decides which tools to invoke based on message content."""

import re

_MATH_RE = re.compile(r'\b\d+\s*[\+\-\*\/\^]\s*\d+\b')
_SEARCH_TRIGGERS = [
    "current", "latest", "today", "yesterday", "news", "price", "cost",
    "who won", "what happened", "how much is", "what is the", "when did",
    "where is", "is it true", "recent", "now", "right now",
]


def needs_tools(text: str) -> list[str]:
    """Returns list of tool names needed. Empty = no tools, zero overhead."""
    tools = []
    lowered = text.lower()

    if _MATH_RE.search(text):
        tools.append("calculator")
    if any(t in lowered for t in _SEARCH_TRIGGERS):
        tools.append("web_search")

    return tools
