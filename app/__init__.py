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
    # CORS_ORIGINS is the explicit list. When it isn't set, fall back to the
    # frontend URL this deployment already knows about rather than blocking
    # every cross-origin request — an unset variable was silently making the
    # API unreachable from the very frontend it exists to serve, and the only
    # sign was one warning line at boot.
    _cors_raw = os.getenv("CORS_ORIGINS", "").strip()
    _source = "CORS_ORIGINS"
    if not _cors_raw:
        _cors_raw = ",".join(
            v for v in (os.getenv("FRONTEND_BASE_URL", ""), os.getenv("FRONTEND_URL", ""))
            if v and v.strip()
        )
        _source = "FRONTEND_BASE_URL / FRONTEND_URL"

    cors_origins = [o.strip().rstrip("/") for o in _cors_raw.split(",") if o.strip()]

    if not cors_origins:
        app.logger.error(
            "No CORS origins resolved — the API will reject every browser request. "
            "Set CORS_ORIGINS (comma-separated) or FRONTEND_BASE_URL."
        )
    else:
        app.logger.info("CORS origins (%s): %s", _source, ", ".join(cors_origins))
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

    # Deactivating an account has to end the session, not just block the next
    # login. Access tokens live 24 hours, and nothing in the request path used
    # to look at `status`, so a deactivated admin kept working — settings,
    # channels, the Graph API proxy — for up to a day after being switched off.
    # Offboarding is the whole point of that control on the Users page.
    #
    # This runs on every @jwt_required() route, so the rule holds in one place
    # rather than needing a status check added to each of them (and remembered
    # for every route added later). Deleted accounts fail here too.
    @jwt.token_in_blocklist_loader
    def account_no_longer_active(jwt_header, jwt_data):
        from app.models import AuthUser
        try:
            uid = jwt_data.get('sub')
            user = AuthUser.query.get(int(uid)) if uid is not None else None
        except (TypeError, ValueError):
            return True
        return (user is None) or (user.status != 'active')

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_data):
        return jsonify({'error': 'This account is no longer active. Please sign in again.'}), 401

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