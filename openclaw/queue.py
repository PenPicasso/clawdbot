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
from dataclasses import dataclass
from typing import Optional, List

from openclaw import config
from openclaw.utils import get_logger, next_retry_at

logger = get_logger(__name__)

DB_PATH = config.SQLITE_DB_PATH

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
    next_retry_at REAL
);

CREATE INDEX IF NOT EXISTS idx_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_next_retry ON jobs(next_retry_at);
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


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_INIT_SQL)
        await db.commit()
    logger.info(f"Job queue DB initialised at {DB_PATH}")


async def create_job(chat_id: int, ack_msg_id: int, prompt: str) -> int:
    now = time.time()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO jobs (chat_id, ack_msg_id, prompt, status, retries, created_at, updated_at, next_retry_at) "
            "VALUES (?, ?, ?, 'pending', 0, ?, ?, ?)",
            (chat_id, ack_msg_id, prompt, now, now, now),
        )
        await db.commit()
        job_id = cursor.lastrowid
    logger.info(f"Job #{job_id} created for chat {chat_id}")
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
    )
