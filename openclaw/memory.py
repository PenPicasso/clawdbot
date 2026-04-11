"""Memory system — conversation history + key facts + shared knowledge."""

import time
import aiosqlite

from openclaw import config
from openclaw.utils import get_logger

logger = get_logger(__name__)

DB_PATH = config.SQLITE_DB_PATH


async def recall(user_id: str, limit: int = 20) -> str:
    """Returns formatted memory context string for injection into prompts."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # Conversation history (private to user)
            cursor = await db.execute(
                "SELECT role, content FROM conversations WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            )
            history = list(reversed(await cursor.fetchall()))

            # Per-user key facts
            cursor = await db.execute(
                "SELECT fact FROM user_facts WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
                (user_id,)
            )
            facts = await cursor.fetchall()

        parts = []
        if facts:
            fact_list = "\n".join(f"- {r['fact']}" for r in facts)
            parts.append(f"Known facts about user:\n{fact_list}")

        if history:
            convo_lines = []
            for r in history[-10:]:  # Show last 10 turns max
                content = r["content"][:300]  # Truncate long content
                convo_lines.append(f"{r['role'].upper()}: {content}")
            parts.append("Recent conversation:\n" + "\n".join(convo_lines))

        return "\n\n".join(parts) if parts else ""

    except Exception as e:
        logger.warning(f"memory.recall failed for user {user_id}: {e}")
        return ""


async def store(user_id: str, role: str, content: str, task_type: str = "simple") -> None:
    """Store a conversation turn. Fire-and-forget safe."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO conversations (user_id, role, content, task_type, created_at) VALUES (?,?,?,?,?)",
                (user_id, role, content[:2000], task_type, time.time())
            )

            # Keep last 100 turns per user (prune old)
            await db.execute(
                """DELETE FROM conversations WHERE user_id=? AND id NOT IN (
                    SELECT id FROM conversations WHERE user_id=? ORDER BY created_at DESC LIMIT 100
                )""",
                (user_id, user_id)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"memory.store failed for user {user_id}: {e}")


async def teach_shared(user_id: str, topic: str, content: str, fast_model_fn) -> str:
    """
    Store to shared_knowledge only via explicit /teach command.
    Runs fast model PII/safety filter first.
    Returns: "stored" | "rejected: <reason>"
    """
    screen_prompt = (
        f"Does this contain PII (names, phone numbers, emails, addresses), "
        f"sensitive personal info, or clearly false claims? Answer YES or NO only.\n\n"
        f"Content: {content}"
    )

    try:
        verdict = await fast_model_fn(screen_prompt)
        if "YES" in verdict.upper():
            return "rejected: content contains sensitive information"

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO shared_knowledge (topic, content, source_user, created_at) VALUES (?,?,?,?)",
                (topic, content[:1000], user_id, time.time())
            )
            await db.commit()
        return "stored"
    except Exception as e:
        logger.error(f"teach_shared failed: {e}")
        return f"rejected: storage error"


async def recall_shared(query: str, limit: int = 5) -> str:
    """Simple keyword match on shared_knowledge topics."""
    keywords = [w.lower() for w in query.split() if len(w) > 3]
    if not keywords:
        return ""

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT topic, content FROM shared_knowledge ORDER BY access_count DESC LIMIT 50"
            )
            rows = await cursor.fetchall()

        matches = []
        for row in rows:
            topic = row["topic"].lower()
            content = row["content"].lower()
            if any(kw in topic or kw in content for kw in keywords):
                matches.append(f"[{row['topic']}] {row['content'][:300]}")
            if len(matches) >= limit:
                break
        return "\n".join(matches) if matches else ""

    except Exception as e:
        logger.warning(f"recall_shared failed: {e}")
        return ""
