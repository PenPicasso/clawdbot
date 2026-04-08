"""
Model clients and router for OpenClaw.

fast_complete()  → Ollama (local, Gemma E4B, <15s)
hf_infer()       → HF Space (Gemma 27B, up to 5 min)
route()          → decides which model to use based on message content
"""

import httpx
from openclaw import config
from openclaw.utils import get_logger

logger = get_logger(__name__)

# Keywords that trigger the deep 27B model
DEEP_KEYWORDS = {
    "analyze", "analysis", "analyse", "deep", "research",
    "breakdown", "break down", "detailed report", "compare",
    "comparison", "evaluate", "evaluation", "comprehensive",
    "step by step", "step-by-step", "elaborate", "in depth",
    "in-depth", "thorough", "thoroughly", "pros and cons",
    "advantages and disadvantages", "explain in detail",
    "full explanation", "critique", "investigate",
}


def route(text: str) -> str:
    """Return 'fast' or 'deep' based on message content."""
    lowered = text.lower()
    if any(kw in lowered for kw in DEEP_KEYWORDS):
        return "deep"
    # Long messages also warrant deeper analysis
    if len(text) > 300:
        return "deep"
    return "fast"


async def fast_complete(prompt: str) -> str:
    """
    Call Ollama (local) for a fast E4B response.
    Returns the model output string, or an error message if Ollama is down.
    """
    payload = {
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=config.FAST_INFER_TIMEOUT) as client:
            resp = await client.post(
                f"{config.OLLAMA_BASE_URL}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
    except httpx.TimeoutException:
        logger.error("Ollama timed out")
        return "Sorry, the fast model timed out. Please try again."
    except Exception as exc:
        logger.error(f"Ollama error: {exc}")
        return f"Sorry, the fast model is temporarily unavailable ({type(exc).__name__})."


async def hf_infer(prompt: str) -> str:
    """
    Call the HF Space inference endpoint.
    Falls back to the HF Inference API if the Space fails.
    Raises on total failure so the poller can handle retries.
    """
    # --- Option A: own HF Space ---
    try:
        result = await _call_hf_space(prompt)
        logger.info("HF Space inference succeeded")
        return result
    except Exception as exc:
        logger.warning(f"HF Space failed ({exc}), trying HF Inference API...")

    # --- Option B: HF Inference API (free tier, rate-limited) ---
    if config.HF_API_TOKEN:
        try:
            result = await _call_hf_inference_api(prompt)
            logger.info("HF Inference API succeeded (fallback)")
            return result
        except Exception as exc:
            logger.error(f"HF Inference API also failed: {exc}")

    raise RuntimeError("Both HF Space and HF Inference API failed")


async def _call_hf_space(prompt: str) -> str:
    headers = {}
    if config.HF_SPACE_SECRET:
        headers["X-OpenClaw-Secret"] = config.HF_SPACE_SECRET

    async with httpx.AsyncClient(timeout=config.HF_INFER_TIMEOUT) as client:
        resp = await client.post(
            f"{config.HF_SPACE_URL}/infer",
            json={"prompt": prompt, "max_tokens": 1024},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()["result"]


async def _call_hf_inference_api(prompt: str) -> str:
    headers = {"Authorization": f"Bearer {config.HF_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 1024, "temperature": 0.7},
        "options": {"wait_for_model": True},
    }
    async with httpx.AsyncClient(timeout=config.HF_INFER_TIMEOUT) as client:
        resp = await client.post(
            f"https://api-inference.huggingface.co/models/{config.HF_API_MODEL}",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0].get("generated_text", "").strip()
        raise RuntimeError(f"Unexpected HF API response: {data}")


async def hf_health_check() -> bool:
    """Ping the HF Space /health endpoint. Returns True if alive."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{config.HF_SPACE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False
