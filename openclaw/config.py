"""
OpenClaw configuration — all settings loaded from .env at import time.
Any missing required variable raises immediately with a clear message.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(
            f"[OpenClaw] Required environment variable '{key}' is missing. "
            f"Check your .env file at {_env_path}"
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# --- Telegram ---
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRET: str = _require("TELEGRAM_WEBHOOK_SECRET")
WEBHOOK_BASE_URL: str = _require("WEBHOOK_BASE_URL")  # e.g. https://yourname.duckdns.org

# --- Fast model (Ollama, local on VM) ---
OLLAMA_BASE_URL: str = _optional("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = _optional("OLLAMA_MODEL", "gemma3:4b")

# --- Deep model (Hugging Face Space) ---
HF_SPACE_URL: str = _require("HF_SPACE_URL")   # e.g. https://user-clawdbot-27b.hf.space
HF_SPACE_SECRET: str = _optional("HF_SPACE_SECRET", "")
HF_API_TOKEN: str = _optional("HF_API_TOKEN", "")  # HF read token for Inference API fallback
HF_API_MODEL: str = _optional("HF_API_MODEL", "google/gemma-3-27b-it")

# --- Storage ---
SQLITE_DB_PATH: str = _optional("SQLITE_DB_PATH", "/opt/openclaw/data/jobs.db")

# --- Admin ---
ADMIN_CHAT_ID: int = int(_require("ADMIN_CHAT_ID"))

# --- Poller tuning ---
POLL_INTERVAL_SECONDS: int = int(_optional("POLL_INTERVAL_SECONDS", "30"))
KEEPALIVE_INTERVAL_SECONDS: int = int(_optional("KEEPALIVE_INTERVAL_SECONDS", "240"))  # 4 min
MAX_RETRIES: int = int(_optional("MAX_RETRIES", "3"))
HF_INFER_TIMEOUT: int = int(_optional("HF_INFER_TIMEOUT", "300"))  # 5 minutes
FAST_INFER_TIMEOUT: int = int(_optional("FAST_INFER_TIMEOUT", "15"))

# --- Scheduler (cron in user's local time) ---
BRIEFING_HOUR: int = int(_optional("BRIEFING_HOUR", "8"))
BRIEFING_MINUTE: int = int(_optional("BRIEFING_MINUTE", "0"))
TIMEZONE: str = _optional("TIMEZONE", "UTC")
