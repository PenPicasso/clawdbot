"""
Background async poller — the engine that drives deep analysis jobs.

Runs as an asyncio.create_task() inside the FastAPI process.
Every POLL_INTERVAL_SECONDS it:
  1. Fetches pending/retryable jobs from SQLite
  2. Sends each to HF Space (sequentially — CPU Space has no parallelism)
  3. Edits the Telegram ACK message with the result
  4. Handles retries with exponential backoff
  5. Falls back to E4B after MAX_RETRIES exhausted
  6. Sends a keep-alive ping to HF Space every 4 minutes to prevent sleep
"""

import asyncio
import time

from telegram import Bot
from telegram.constants import ParseMode

from openclaw import config, queue as q, models
from openclaw import agent as agent_loop
from openclaw.classifier import classify
from openclaw.utils import (
    get_logger,
    format_deep_result,
    format_fallback_result,
    truncate_for_telegram,
)

logger = get_logger(__name__)


async def run_poller(bot: Bot) -> None:
    """Main poller loop. Never returns (runs until process exits)."""
    logger.info("Poller started")
    last_keepalive = 0.0

    while True:
        try:
            # --- Keep-alive ping to prevent HF Space from sleeping ---
            now = time.time()
            if now - last_keepalive >= config.KEEPALIVE_INTERVAL_SECONDS:
                alive = await models.hf_health_check()
                if not alive:
                    logger.warning("HF Space keep-alive ping failed (Space may be sleeping)")
                last_keepalive = now

            # --- Process pending jobs ---
            jobs = await q.get_pending_jobs()
            if jobs:
                logger.info(f"Processing {len(jobs)} pending job(s)")

            for job in jobs:
                await _process_job(bot, job)

        except Exception as exc:
            logger.error(f"Poller loop error (will continue): {exc}", exc_info=True)

        await asyncio.sleep(config.POLL_INTERVAL_SECONDS)


async def _process_job(bot: Bot, job: q.Job) -> None:
    logger.info(f"Processing job #{job.id} (retries={job.retries})")
    await q.mark_processing(job.id)

    try:
        # Determine task_type from job (with fallback to classifier)
        task_type = job.task_type or classify(job.prompt)

        # Warm up HF Space before complex jobs (avoid cold-start surprises)
        if task_type == "complex":
            healthy = await models.hf_health_check()
            if not healthy:
                logger.info("HF Space warming up, waiting 60s before complex job...")
                await _edit_ack(
                    bot,
                    job.chat_id,
                    job.ack_msg_id,
                    "⚙️ Athena is warming up the deep analysis engine... (~60s)",
                )
                await asyncio.sleep(60)

        # Run the adaptive agent loop
        result = await agent_loop.run(
            job_id=job.id,
            prompt=job.prompt,
            task_type=task_type,
            user_id=str(job.chat_id),
            log_fn=q.log_agent_run,
        )

        await q.mark_done(job.id, result)
        formatted = format_deep_result(result)
        await _edit_ack(bot, job.chat_id, job.ack_msg_id, formatted)
        logger.info(f"Job #{job.id} completed and sent to Telegram")

    except Exception as exc:
        logger.warning(f"Job #{job.id} inference failed: {exc}")

        if job.retries < config.MAX_RETRIES:
            # Schedule retry with backoff
            await q.mark_failed(job.id, job.retries)
            retry_num = job.retries + 1
            delay = [30, 60, 120][min(job.retries, 2)]
            await _edit_ack(
                bot,
                job.chat_id,
                job.ack_msg_id,
                f"⏳ *Deep analysis delayed* (attempt {retry_num}/{config.MAX_RETRIES})\n"
                f"_Retrying in ~{delay}s..._",
            )
        else:
            # All retries exhausted — fall back to fast model
            logger.warning(f"Job #{job.id} exhausted retries, using E4B fallback")
            await _send_admin_alert(
                bot,
                f"⚠️ Job #{job.id} fell back to E4B after {config.MAX_RETRIES} HF failures.\n"
                f"Prompt: {job.prompt[:100]}",
            )
            try:
                fallback = await models.fast_complete(job.prompt)
            except Exception:
                fallback = "Sorry, both models are currently unavailable. Please try again later."

            await q.mark_fallback(job.id, fallback)
            formatted = format_fallback_result(fallback)
            await _edit_ack(bot, job.chat_id, job.ack_msg_id, formatted)


async def _edit_ack(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=truncate_for_telegram(text),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.error(f"Failed to edit message {message_id} in chat {chat_id}: {exc}")
        # If editing fails (e.g. message too old), send a new message
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=truncate_for_telegram(text),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc2:
            logger.error(f"Fallback send also failed: {exc2}")


async def _send_admin_alert(bot: Bot, text: str) -> None:
    try:
        await bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.error(f"Admin alert failed: {exc}")
