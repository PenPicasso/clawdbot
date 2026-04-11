"""OpenClaw tools — calculator, web search, and tool router."""

from openclaw.tools.calculator import calculate
from openclaw.tools.web_search import search as web_search
from openclaw.tools.router import needs_tools

__all__ = ["calculate", "web_search", "needs_tools"]
