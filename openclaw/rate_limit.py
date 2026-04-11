"""Per-user and global rate limiting for task types."""

import time
import aiosqlite

from openclaw import config
from openclaw.utils import get_logger

logger = get_logger(__name__)

DB_PATH = config.SQLITE_DB_PATH


async def check(user_id: str, task_type: str) -> tuple[bool, str]:
    """
    Check if a user can perform a task.
    Returns (allowed, reason). If allowed=False, reason explains why.
    """
    now = time.time()
    window = now - 3600  # 1 hour window

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Per-user check for complex
            if task_type == "complex":
                cursor = await db.execute(
                    "SELECT COUNT(*) as cnt FROM jobs WHERE chat_id=? AND task_type='complex' AND created_at>?",
                    (user_id, window)
                )
                row = await cursor.fetchone()
                if row and row["cnt"] >= config.RATE_LIMIT_COMPLEX_PER_HOUR:
                    return False, f"Complex job limit reached ({config.RATE_LIMIT_COMPLEX_PER_HOUR}/hour). Try /ask for a faster response."

            # Per-user check for medium
            if task_type == "medium":
                cursor = await db.execute(
                    "SELECT COUNT(*) as cnt FROM jobs WHERE chat_id=? AND task_type='medium' AND created_at>?",
                    (user_id, window)
                )
                row = await cursor.fetchone()
                if row and row["cnt"] >= config.RATE_LIMIT_MEDIUM_PER_HOUR:
                    return False, f"Rate limit reached for medium analysis. Try again in an hour."

            # Global check (all users, all non-done jobs)
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status NOT IN ('done','fallback') AND created_at>?",
                (window,)
            )
            row = await cursor.fetchone()
            if row and row["cnt"] >= config.RATE_LIMIT_GLOBAL_PER_HOUR:
                return False, "System is busy. Try again in a few minutes."

    except Exception as e:
        logger.error(f"rate_limit.check failed: {e}")
        # On error, allow the request (don't block on DB issues)
        return True, ""

    return True, ""
