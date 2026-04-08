"""
Shared utilities: logger, retry decorator, Telegram helpers.
"""

import asyncio
import logging
import functools
import time
from typing import Callable, Any

# --- Logger ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


# --- Retry decorator (async) ---
def retry_async(max_retries: int = 3, backoff_base: float = 2.0):
    """
    Retries an async function up to max_retries times with exponential backoff.
    Raises the last exception if all attempts fail.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> Any:
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        wait = backoff_base ** attempt
                        logging.getLogger(__name__).warning(
                            f"{fn.__name__} attempt {attempt + 1} failed: {exc}. "
                            f"Retrying in {wait:.0f}s..."
                        )
                        await asyncio.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


# --- Telegram text helpers ---
TELEGRAM_MAX_LEN = 4096


def truncate_for_telegram(text: str, max_len: int = TELEGRAM_MAX_LEN) -> str:
    if len(text) <= max_len:
        return text
    suffix = "\n\n[... truncated — response exceeded Telegram's 4096 character limit]"
    return text[: max_len - len(suffix)] + suffix


def format_deep_result(result: str) -> str:
    header = "🔬 *Deep Analysis Complete*\n\n"
    return truncate_for_telegram(header + result)


def format_fallback_result(result: str) -> str:
    header = "⚡ *Fast Response* _(deep model unavailable after 3 retries)_\n\n"
    return truncate_for_telegram(header + result)


# --- Backoff schedule for failed jobs ---
BACKOFF_SCHEDULE = [30, 60, 120]  # seconds after retry 0, 1, 2


def next_retry_at(retries: int) -> float:
    delay = BACKOFF_SCHEDULE[min(retries, len(BACKOFF_SCHEDULE) - 1)]
    return time.time() + delay
