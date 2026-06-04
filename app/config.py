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

    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-key-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = 86400  # 24 hours in seconds

    # Anthropic Claude (replaces OpenAI)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "400"))

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
