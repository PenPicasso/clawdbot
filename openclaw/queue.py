"""
SQLite job queue for deep-analysis requests.

Schema:
  jobs(id, chat_id, ack_msg_id, prompt, status, result, retries, created_at, next_retry_at)

Status values:
  pending    — waiting to be sent to HF
  processing — currently in-flight to HF
  done       — HF returned a result, Telegram notified
  failed     — a single attempt failed; will be retried
  fallback   — all retries exhausted; E4B used as fallback
"""

import time
import aiosqlite
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional, List

from openclaw import config
from openclaw.utils import get_logger, next_retry_at

logger = get_logger(__name__)

DB_PATH = config.SQLITE_DB_PATH


@asynccontextmanager
async def get_db():
    """Async context manager for database connections."""
    async with aiosqlite.connect(DB_PATH) as db:
        yield db

_INIT_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER NOT NULL,
    ack_msg_id    INTEGER NOT NULL,
    prompt        TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    result        TEXT,
    retries       INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    next_retry_at REAL,
    task_type     TEXT DEFAULT 'medium',
    budget_seconds INTEGER DEFAULT 90
);

CREATE INDEX IF NOT EXISTS idx_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_next_retry ON jobs(next_retry_at);

CREATE TABLE IF NOT EXISTS agent_runs (
    id            INTEGER PRIMARY KEY,
    job_id        INTEGER,
    user_id       TEXT NOT NULL,
    task_type     TEXT NOT NULL,
    prompt        TEXT NOT NULL,
    plan          TEXT,
    steps_json    TEXT,
    tools_called  TEXT,
    final_result  TEXT,
    critique_score REAL,
    iterations    INTEGER DEFAULT 0,
    elapsed_ms    INTEGER,
    status        TEXT NOT NULL,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY,
    user_id       TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    task_type     TEXT,
    created_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, created_at);

CREATE TABLE IF NOT EXISTS user_facts (
    id            INTEGER PRIMARY KEY,
    user_id       TEXT NOT NULL,
    fact          TEXT NOT NULL,
    confidence    REAL DEFAULT 1.0,
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS shared_knowledge (
    id            INTEGER PRIMARY KEY,
    topic         TEXT NOT NULL,
    content       TEXT NOT NULL,
    source_user   TEXT,
    created_at    REAL NOT NULL,
    access_count  INTEGER DEFAULT 0
);
"""


@dataclass
class Job:
    id: int
    chat_id: int
    ack_msg_id: int
    prompt: str
    status: str
    result: Optional[str]
    retries: int
    created_at: float
    updated_at: float
    next_retry_at: Optional[float]
    task_type: Optional[str] = "medium"
    budget_seconds: Optional[int] = 90


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_INIT_SQL)

        # Migration: add new columns to jobs table if they don't exist
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN task_type TEXT DEFAULT 'medium'")
        except Exception:
            pass  # Column may already exist
        try:
            await db.execute("ALTER TABLE jobs ADD COLUMN budget_seconds INTEGER DEFAULT 90")
        except Exception:
            pass  # Column may already exist

        # Stuck-job recovery: reset processing→pending for jobs stuck >30 min
        stuck_threshold = time.time() - 1800  # 30 minutes
        await db.execute(
            "UPDATE jobs SET status='pending', retries=retries+1 "
            "WHERE status='processing' AND updated_at < ?",
            (stuck_threshold,)
        )

        await db.commit()
    logger.info(f"Job queue DB initialised at {DB_PATH}")


async def create_job(chat_id: int, ack_msg_id: int, prompt: str, task_type: str = "medium") -> int:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO jobs (chat_id, ack_msg_id, prompt, status, retries, created_at, updated_at, next_retry_at, task_type) "
            "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?)",
            (chat_id, ack_msg_id, prompt, now, now, now, task_type),
        )
        await db.commit()
        job_id = cursor.lastrowid
    logger.info(f"Job #{job_id} created for chat {chat_id} (task_type={task_type})")
    return job_id


async def get_pending_jobs() -> List[Job]:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE status IN ('pending', 'failed') AND next_retry_at <= ? ORDER BY created_at ASC",
            (now,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_job(r) for r in rows]


async def mark_processing(job_id: int) -> None:
    await _update_status(job_id, "processing")


async def mark_done(job_id: int, result: str) -> None:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status='done', result=?, updated_at=? WHERE id=?",
            (result, now, job_id),
        )
        await db.commit()
    logger.info(f"Job #{job_id} done")


async def mark_failed(job_id: int, retries: int) -> None:
    now = time.time()
    nra = next_retry_at(retries)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status='failed', retries=?, updated_at=?, next_retry_at=? WHERE id=?",
            (retries + 1, now, nra, job_id),
        )
        await db.commit()
    logger.warning(f"Job #{job_id} failed (attempt {retries + 1}), retry at {nra:.0f}")


async def mark_fallback(job_id: int, result: str) -> None:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status='fallback', result=?, updated_at=? WHERE id=?",
            (result, now, job_id),
        )
        await db.commit()
    logger.warning(f"Job #{job_id} fell back to E4B")


async def get_recent_jobs(limit: int = 10) -> List[Job]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_job(r) for r in rows]


async def cleanup_old_jobs(days: int = 30) -> int:
    cutoff = time.time() - days * 86400
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM jobs WHERE status IN ('done', 'fallback', 'failed') AND created_at < ?",
            (cutoff,),
        )
        await db.commit()
        deleted = cursor.rowcount
    if deleted:
        logger.info(f"Cleaned up {deleted} old jobs")
    return deleted


async def _update_status(job_id: int, status: str) -> None:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status=?, updated_at=? WHERE id=?",
            (status, now, job_id),
        )
        await db.commit()


def _row_to_job(row) -> Job:
    return Job(
        id=row["id"],
        chat_id=row["chat_id"],
        ack_msg_id=row["ack_msg_id"],
        prompt=row["prompt"],
        status=row["status"],
        result=row["result"],
        retries=row["retries"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        next_retry_at=row["next_retry_at"],
        task_type=row.get("task_type", "medium"),
        budget_seconds=row.get("budget_seconds", 90),
    )


async def log_agent_run(
    job_id: int, task_type: str, prompt: str, plan: str,
    steps: list, tools: list, result: str, score, iterations: int,
    elapsed_ms: int, status: str, user_id: str
) -> None:
    """Log an agent run to the database."""
    import json
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO agent_runs
                   (job_id, user_id, task_type, prompt, plan, steps_json, tools_called,
                    final_result, critique_score, iterations, elapsed_ms, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id, user_id, task_type, prompt[:500], plan[:2000] if plan else None,
                 json.dumps(steps), json.dumps(tools), result[:3000] if result else None,
                 score, iterations, elapsed_ms, status, time.time())
            )
            await db.commit()
    except Exception as e:
        logger.error(f"log_agent_run failed: {e}")


async def count_pending() -> int:
    """Count jobs that are pending or processing."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status IN ('pending', 'processing')"
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.error(f"count_pending failed: {e}")
        return 0
