"""
Telegram message handling for ClawDBot.

All incoming Telegram updates are processed here.
The bot does NOT talk to HF directly — complex requests
are written to the job queue and handled by the poller.
"""

import time
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

from openclaw import config
from openclaw import queue as q
from openclaw import models
from openclaw import memory as mem
from openclaw.classifier import classify
from openclaw import rate_limit
from openclaw.utils import get_logger, truncate_for_telegram

logger = get_logger(__name__)


# --- Build the Application (called once from main.py) ---
def build_application() -> Application:
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("deep", cmd_deep))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("teach", cmd_teach))
    app.add_handler(CommandHandler("budget", cmd_budget))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


# --- Command handlers ---

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 *Welcome to ClawDBot!*\n\n"
        "I use two AI models:\n"
        "⚡ *Fast (E4B)* — instant replies for chat & quick questions\n"
        "🔬 *Deep (27B)* — queued analysis for complex requests (2–15 min)\n\n"
        "*Commands:*\n"
        "/ask `<question>` — force fast response\n"
        "/deep `<question>` — force deep analysis\n"
        "/status — show queue status\n"
        "/help — full guide\n\n"
        "Just send a message and I'll route it automatically. "
        "Use words like *analyze*, *research*, *compare*, or *breakdown* to trigger deep mode."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *ClawDBot Help*\n\n"
        "*How routing works:*\n"
        "• Short questions → Fast model (instant)\n"
        "• 'analyze', 'research', 'deep', 'compare', 'breakdown' → Deep model (queued)\n"
        "• Messages over 300 characters → Deep model\n\n"
        "*Commands:*\n"
        "`/ask <text>` — always use fast model\n"
        "`/deep <text>` — always queue for deep model\n"
        "`/status` — show pending jobs and recent results\n\n"
        "*Deep analysis flow:*\n"
        "1. You send a complex query\n"
        "2. I reply 'Queued for deep analysis...'\n"
        "3. I edit that message with the result when ready\n"
        "4. If deep model fails 3× → fast model fallback\n\n"
        "*Tip:* Use /ask when you just want a quick answer."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    prompt = " ".join(ctx.args) if ctx.args else ""
    if not prompt.strip():
        await update.message.reply_text("Usage: /ask <your question>")
        return
    await _fast_reply(update, prompt)


async def cmd_deep(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    prompt = " ".join(ctx.args) if ctx.args else ""
    if not prompt.strip():
        await update.message.reply_text("Usage: /deep <your question>")
        return
    await _queue_deep(update, prompt, "complex")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = await q.get_recent_jobs(limit=5)
    if not jobs:
        await update.message.reply_text("No jobs in the queue yet.")
        return

    lines = ["📊 *Recent Jobs (last 5):*\n"]
    status_emoji = {
        "pending": "⏳",
        "processing": "⚙️",
        "done": "✅",
        "failed": "❌",
        "fallback": "⚡",
    }
    for job in jobs:
        emoji = status_emoji.get(job.status, "❓")
        age = int((time.time() - job.created_at) / 60)
        preview = job.prompt[:50].replace("\n", " ") + ("..." if len(job.prompt) > 50 else "")
        lines.append(f"{emoji} #{job.id} [{job.status}] {age}m ago — _{preview}_")

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.MARKDOWN
    )


async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin only. Shows last 5 agent runs."""
    if str(update.effective_chat.id) != str(config.ADMIN_CHAT_ID):
        return

    async with q.get_db() as db:
        rows = await db.execute_fetchall(
            """SELECT task_type, status, elapsed_ms, critique_score, created_at
               FROM agent_runs ORDER BY created_at DESC LIMIT 5"""
        )

    if not rows:
        await update.message.reply_text("No agent runs yet.")
        return

    lines = ["*Last 5 agent runs:*\n"]
    for task_type, status, elapsed_ms, critique_score, created_at in rows:
        elapsed = f"{elapsed_ms/1000:.1f}s" if elapsed_ms else "?"
        score = f" score={critique_score:.0f}" if critique_score else ""
        lines.append(f"• {task_type} | {status} | {elapsed}{score}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_teach(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """/teach <topic> | <content> — stores to shared knowledge base."""
    text = " ".join(ctx.args) if ctx.args else ""
    if "|" not in text:
        await update.message.reply_text("Usage: /teach <topic> | <content>")
        return

    topic, content = text.split("|", 1)
    result = await mem.teach_shared(
        str(update.effective_chat.id),
        topic.strip(),
        content.strip(),
        models.fast_complete,
    )
    await update.message.reply_text(f"Knowledge: {result}")


async def cmd_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin only. Shows budget config and last job timings."""
    if str(update.effective_chat.id) != str(config.ADMIN_CHAT_ID):
        return

    async with q.get_db() as db:
        rows = await db.execute_fetchall(
            "SELECT task_type, elapsed_ms FROM agent_runs ORDER BY created_at DESC LIMIT 10"
        )

    from openclaw.agent import BUDGETS

    lines = [
        f"*Budgets:* simple={BUDGETS['simple']}s medium={BUDGETS['medium']}s complex={BUDGETS['complex']}s"
    ]
    lines.append("*Recent elapsed times:*")
    for task_type, elapsed_ms in rows:
        elapsed = f"{elapsed_ms/1000:.1f}s" if elapsed_ms else "?"
        lines.append(f"• {task_type}: {elapsed}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# --- Plain message handler ---

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if not text.strip():
        return

    task_type = classify(text)
    user_id = str(update.effective_chat.id)

    if task_type == "simple":
        await _fast_reply(update, text)
        return

    # Rate limit check before queuing
    allowed, reason = await rate_limit.check(user_id, task_type)
    if not allowed:
        await update.message.reply_text(f"⏸ {reason}")
        return

    await _queue_deep(update, text, task_type)


# --- Helpers ---

async def _fast_reply(update: Update, prompt: str) -> None:
    # Show typing indicator
    await update.message.chat.send_action("typing")
    result = await models.fast_complete(prompt)
    await update.message.reply_text(
        truncate_for_telegram(result),
        parse_mode=ParseMode.MARKDOWN,
    )


async def _queue_deep(update: Update, prompt: str, task_type: str) -> None:
    # Count pending jobs for queue position
    pending = await q.count_pending()
    position_str = f" (position {pending + 1} in queue)" if pending > 0 else ""
    est_str = " · est. 2–5 min" if task_type == "medium" else " · est. 10–15 min"

    # Send immediate ACK — we'll edit this message when the result is ready
    ack = await update.message.reply_text(
        f"⚙️ Queued for {'analysis' if task_type == 'medium' else 'deep research'}"
        f"{position_str}{est_str}",
        parse_mode=ParseMode.MARKDOWN,
    )
    chat_id = update.effective_chat.id
    await q.create_job(chat_id, ack.message_id, prompt, task_type)
    logger.info(f"Queued {task_type} job for chat {chat_id}")


# --- Utility for sending admin alerts (called from poller/scheduler) ---
async def send_admin_message(bot: Bot, text: str) -> None:
    try:
        await bot.send_message(
            chat_id=config.ADMIN_CHAT_ID,
            text=truncate_for_telegram(text),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.error(f"Failed to send admin message: {exc}")
