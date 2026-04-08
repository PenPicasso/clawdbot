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
    await _queue_deep(update, prompt)


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


# --- Plain message handler ---

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    if not text.strip():
        return

    decision = models.route(text)

    if decision == "fast":
        await _fast_reply(update, text)
    else:
        await _queue_deep(update, text)


# --- Helpers ---

async def _fast_reply(update: Update, prompt: str) -> None:
    # Show typing indicator
    await update.message.chat.send_action("typing")
    result = await models.fast_complete(prompt)
    await update.message.reply_text(
        truncate_for_telegram(result),
        parse_mode=ParseMode.MARKDOWN,
    )


async def _queue_deep(update: Update, prompt: str) -> None:
    # Send immediate ACK — we'll edit this message when the result is ready
    ack = await update.message.reply_text(
        "🔬 *Queued for deep analysis...*\n"
        "_(estimated 2–15 minutes — I'll update this message when done)_",
        parse_mode=ParseMode.MARKDOWN,
    )
    chat_id = update.effective_chat.id
    await q.create_job(chat_id, ack.message_id, prompt)
    logger.info(f"Queued deep job for chat {chat_id}")


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
