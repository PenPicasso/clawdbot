"""
APScheduler-based automated agents.

Jobs:
  - Morning briefing (08:00 daily) → E4B generates summary → send to admin
  - Health check (every 10 min) → ping Ollama + HF Space → alert admin if down
  - DB cleanup (02:00 daily) → remove old completed/failed jobs
"""

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from telegram.constants import ParseMode

from openclaw import config, queue as q, models
from openclaw.utils import get_logger, truncate_for_telegram

logger = get_logger(__name__)

_BRIEFING_PROMPT = (
    "You are a concise morning briefing assistant. Provide today's briefing covering:\n"
    "1. Top 3 world news headlines (brief summaries)\n"
    "2. General market sentiment (crypto + stocks, one sentence each)\n"
    "3. One interesting fact or tip for today\n\n"
    "Keep the entire response under 300 words. Use bullet points. Be factual and neutral."
)


def build_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    # Morning briefing
    scheduler.add_job(
        _morning_briefing,
        CronTrigger(hour=config.BRIEFING_HOUR, minute=config.BRIEFING_MINUTE),
        args=[bot],
        id="morning_briefing",
        name="Morning Briefing",
        replace_existing=True,
    )

    # Health check every 10 minutes
    scheduler.add_job(
        _health_check,
        IntervalTrigger(minutes=10),
        args=[bot],
        id="health_check",
        name="System Health Check",
        replace_existing=True,
    )

    # DB cleanup at 02:00 daily
    scheduler.add_job(
        _db_cleanup,
        CronTrigger(hour=2, minute=0),
        id="db_cleanup",
        name="DB Cleanup",
        replace_existing=True,
    )

    logger.info("Scheduler configured with 3 jobs")
    return scheduler


async def _morning_briefing(bot: Bot) -> None:
    logger.info("Running morning briefing")
    try:
        result = await models.fast_complete(_BRIEFING_PROMPT)
        text = f"☀️ *Morning Briefing*\n\n{result}"
        await bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=truncate_for_telegram(text),
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info("Morning briefing sent")
    except Exception as exc:
        logger.error(f"Morning briefing failed: {exc}")


async def _health_check(bot: Bot) -> None:
    issues = []

    # Check Ollama
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            if resp.status_code != 200:
                issues.append(f"Ollama returned HTTP {resp.status_code}")
    except Exception as exc:
        issues.append(f"Ollama unreachable: {exc}")

    # Check HF Space
    hf_alive = await models.hf_health_check()
    if not hf_alive:
        issues.append("HF Space /health failed (may be sleeping or rebuilding)")

    if issues:
        alert = "⚠️ *OpenClaw Health Alert*\n\n" + "\n".join(f"• {i}" for i in issues)
        try:
            await bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=alert,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:
            logger.error(f"Health alert send failed: {exc}")
    else:
        logger.debug("Health check passed (Ollama ✓, HF Space ✓)")


async def _db_cleanup() -> None:
    deleted = await q.cleanup_old_jobs(days=30)
    logger.info(f"DB cleanup: removed {deleted} old jobs")
