"""
OpenClaw FastAPI entry point.

Startup sequence:
  1. Validate all config (fails fast if .env is incomplete)
  2. Initialise SQLite job queue
  3. Build Telegram Application
  4. Register webhook with Telegram
  5. Start APScheduler
  6. Start background poller as asyncio task

Endpoints:
  POST /webhook/{secret}  — receives all Telegram updates
  GET  /health            — liveness check (returns model status)
  GET  /jobs              — admin view of recent jobs (requires X-Admin-Secret header)
"""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Header, HTTPException
from telegram import Update

from openclaw import config, queue as q
from openclaw import bot as bot_module
from openclaw import poller as poller_module
from openclaw import scheduler as scheduler_module
from openclaw import models
from openclaw.utils import get_logger

logger = get_logger(__name__)

# Global references (set during lifespan startup)
_application = None
_scheduler = None
_poller_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _application, _scheduler, _poller_task

    logger.info("OpenClaw starting up...")

    # 1. Init DB
    await q.init_db()

    # 2. Build Telegram Application
    _application = bot_module.build_application()
    await _application.initialize()
    await _application.start()

    # 3. Register webhook (non-fatal — DNS may not be ready on first boot)
    webhook_url = (
        f"{config.WEBHOOK_BASE_URL}/webhook/{config.TELEGRAM_WEBHOOK_SECRET}"
    )
    try:
        await _application.bot.set_webhook(
            url=webhook_url,
            secret_token=config.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=["message", "edited_message", "callback_query"],
        )
        logger.info(f"Webhook registered: {webhook_url}")
    except Exception as e:
        logger.warning(f"Webhook registration skipped (DNS not ready yet): {e}")

    # 4. Start scheduler
    _scheduler = scheduler_module.build_scheduler(_application.bot)
    _scheduler.start()
    logger.info("Scheduler started")

    # 5. Start background poller
    _poller_task = asyncio.create_task(
        poller_module.run_poller(_application.bot),
        name="hf-poller",
    )
    logger.info("Poller task started")

    logger.info("OpenClaw is ready")

    yield  # Server is running

    # --- Shutdown ---
    logger.info("OpenClaw shutting down...")
    _poller_task.cancel()
    try:
        await _poller_task
    except asyncio.CancelledError:
        pass

    _scheduler.shutdown(wait=False)
    await _application.stop()
    await _application.shutdown()
    logger.info("OpenClaw stopped cleanly")


app = FastAPI(title="OpenClaw", lifespan=lifespan)


# --- Telegram webhook receiver ---
@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> Response:
    if secret != config.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    body = await request.body()
    try:
        data = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update = Update.de_json(data, _application.bot)
    await _application.process_update(update)
    return Response(status_code=200)


# --- Health check ---
@app.get("/health")
async def health():
    ollama_ok = True
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        ollama_ok = False

    jobs = await q.get_recent_jobs(limit=5)
    pending = sum(1 for j in jobs if j.status in ("pending", "processing", "failed"))

    return {
        "status": "ok",
        "ollama": "up" if ollama_ok else "down",
        "pending_jobs": pending,
        "model": config.OLLAMA_MODEL,
        "hf_space": config.HF_SPACE_URL,
    }


# --- Admin job viewer ---
@app.get("/jobs")
async def list_jobs(x_admin_secret: str = Header(default="")):
    if x_admin_secret != config.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403)

    jobs = await q.get_recent_jobs(limit=20)
    return [
        {
            "id": j.id,
            "chat_id": j.chat_id,
            "status": j.status,
            "retries": j.retries,
            "prompt_preview": j.prompt[:80],
            "created_at": j.created_at,
        }
        for j in jobs
    ]
