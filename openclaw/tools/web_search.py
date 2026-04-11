"""DuckDuckGo instant answers web search tool."""

import httpx
from openclaw.utils import get_logger

logger = get_logger(__name__)

DDGR_URL = "https://api.duckduckgo.com/"


async def search(query: str, max_results: int = 3) -> str:
    """DuckDuckGo instant answers. Free, no key. Returns plain text summary."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(DDGR_URL, params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            })
            resp.raise_for_status()
            data = resp.json()

        parts = []
        if data.get("AbstractText"):
            parts.append(data["AbstractText"])

        for r in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(r, dict) and r.get("Text"):
                parts.append(r["Text"])

        return "\n".join(parts) if parts else f"[no results for: {query}]"

    except Exception as e:
        logger.warning(f"web_search failed for '{query}': {e}")
        return f"[search unavailable: {e}]"
