"""
config.py
Loads environment variables and exposes them as a config object.
Flask's app.config is populated from this in create_app().
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_ENV", "development") == "development"

    # Public base URL the webhook receivers are reachable at
    # (e.g. ngrok URL during dev, real domain in prod).
    # Used by GET /api/channels to compose the full webhook URL the user
    # pastes into the Meta/TikTok developer console.
    # If not set, /api/channels falls back to the request's host_url.
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Connection pooling ───────────────────────────────────────────────
    # Two distinct Supabase failures to defend against:
    #
    # 1. STALE CONNECTIONS. The pooler drops idle connections without telling
    #    the client, so one sitting between webhooks is often already dead.
    #    pool_pre_ping checks before handing it out; pool_recycle retires it
    #    before the pooler's own idle timeout can.
    #
    # 2. TOO MANY CONNECTIONS — seen in production as:
    #      FATAL: (EMAXCONNSESSION) max clients reached in session mode
    #    That is the SESSION-mode pooler (port 5432) running out of slots.
    #    Session mode dedicates a server connection to each client for its
    #    whole life, so slots are few. The real fix is to point DATABASE_URL
    #    at the TRANSACTION-mode pooler on port 6543, which returns the
    #    connection after every transaction and supports far more clients.
    #
    # These defaults keep our own footprint small either way. Procfile runs
    # 2 workers x 4 threads, and the pool is PER WORKER PROCESS — so the old
    # 5 + 10 overflow meant up to 30 connections from the web dyno alone,
    # before cron jobs and webhook handlers. pool_size now matches the thread
    # count so threads rarely queue, with only a little overflow on top:
    # (4 + 1) x 2 workers = 10 maximum.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "280")),   # under the pooler's 300s
        "pool_size": int(os.getenv("DB_POOL_SIZE", "4")),           # = gunicorn threads
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "1")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    }

    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-key-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = 86400  # 24 hours in seconds

    # Anthropic Claude (replaces OpenAI)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
    CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "300"))

    # Meta (Instagram + WhatsApp + Facebook)
    META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
    META_APP_SECRET = os.getenv("META_APP_SECRET", "")
    META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

    # Shopify
    SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "")
    SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
    SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")

    # TikTok
    TIKTOK_APP_ID = os.getenv("TIKTOK_APP_ID", "")
    TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    TIKTOK_VERIFY_TOKEN = os.getenv("TIKTOK_VERIFY_TOKEN", "")
