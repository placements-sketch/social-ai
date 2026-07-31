"""
app/__init__.py
Application factory. Creates and configures the Flask app.
"""

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

# Shared instances — imported by models and other modules
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
# Per-route rate limiter (no global default). In-memory is fine for one Render
# instance; point storage_uri at Redis if you ever run multiple instances.
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def create_app():
    from app.config import Config
    import os

    # ── Error monitoring (Sentry) — active only when SENTRY_DSN is set, so
    #    local/dev without the env var is a silent no-op. ──
    _sentry_dsn = os.getenv("SENTRY_DSN")
    if _sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration

        def _scrub_sensitive(event, hint):
            # Never ship auth tokens to Sentry — strip the Authorization header.
            try:
                headers = (event.get("request") or {}).get("headers") or {}
                for k in list(headers.keys()):
                    if k.lower() == "authorization":
                        headers[k] = "[Filtered]"
            except Exception:
                pass
            return event

        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[FlaskIntegration()],
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            release=os.getenv("RENDER_GIT_COMMIT") or None,   # ties errors to the deploy
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            send_default_pii=False,
            before_send=_scrub_sensitive,
        )

    app = Flask(__name__)
    app.config.from_object(Config)

    # Render terminates TLS at its proxy and forwards the real client IP in
    # X-Forwarded-For. Trust one hop so request.remote_addr — and the limiter's
    # per-IP keying — reflect the actual client, not the shared proxy IP.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({'error': 'Too many requests. Please slow down and try again shortly.'}), 429

    # Enable CORS for frontend
    import os
    _cors_raw = os.getenv("CORS_ORIGINS", "").strip()
    if not _cors_raw:
        app.logger.warning("CORS_ORIGINS not set — cross-origin requests will be blocked. Set it to your frontend URL.")
    cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    CORS(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        supports_credentials=True,
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )
    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_data):
        return jsonify({'error': 'Token has expired'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return jsonify({'error': 'Invalid token'}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return jsonify({'error': 'Missing authorization token'}), 401

    # Register blueprints
    try:
        from app.routes import bp
        from app.auth import auth_bp
        from app.messages import messages_bp
        from app.channels import channels_bp
        from app.products import products_bp
        from app.ai_settings import ai_settings_bp
        from app.automation import automation_bp
        from app.logs import logs_bp
        from app.assignment import assignment_bp
        from app.analytics import analytics_bp
        from app.customers import customers_bp
        from app.orders import orders_bp
        from app.notifications import notifications_bp
        from app.store_info_routes import store_info_bp
        from app.auth_meta import auth_meta_bp
        from app.auth_instagram import auth_ig_bp
        from app.cron_routes import cron_bp
        from app.health import health_bp
        from app.settings import settings_bp
        from app.ai_assistant import ai_assistant_bp
        from app.meta_test import meta_test_bp

        app.register_blueprint(bp)
        app.register_blueprint(auth_bp)
        app.register_blueprint(messages_bp)
        app.register_blueprint(channels_bp)
        app.register_blueprint(products_bp)
        app.register_blueprint(ai_settings_bp)
        app.register_blueprint(automation_bp)
        app.register_blueprint(logs_bp)
        app.register_blueprint(assignment_bp)
        app.register_blueprint(analytics_bp)
        app.register_blueprint(customers_bp)
        app.register_blueprint(orders_bp)
        app.register_blueprint(notifications_bp)
        app.register_blueprint(store_info_bp)
        app.register_blueprint(auth_meta_bp)
        app.register_blueprint(auth_ig_bp)
        app.register_blueprint(cron_bp)
        app.register_blueprint(health_bp)
        app.register_blueprint(settings_bp)
        app.register_blueprint(ai_assistant_bp, url_prefix='/api')
        app.register_blueprint(meta_test_bp)

        print("[APP] All blueprints registered successfully")
    except Exception as e:
        print(f"[APP ERROR] Failed to register blueprints: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
    
    # Import models so Flask-Migrate can detect them
    with app.app_context():
        try:
            from app import models  # noqa: F401
            print("[APP] Models imported successfully")
        except Exception as e:
            print(f"[APP ERROR] Failed to import models: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    # Instagram DM poller is RETIRED — webhook-only. New DMs/comments arrive via
    # /webhook/instagram as they happen; we never backfill history. Do not
    # re-enable start_poller.

    return app