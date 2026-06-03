"""
app/__init__.py
Application factory. Creates and configures the Flask app.
"""

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from config import Config

# Shared instances — imported by models and other modules
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # Enable CORS for frontend
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

    # JWT error handlers
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_data):
        print("[JWT] Token expired")
        return jsonify({'error': 'Token has expired'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        print(f"[JWT] Invalid token: {error}")
        return jsonify({'error': 'Invalid token'}), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        print(f"[JWT] Missing token: {error}")
        return jsonify({'error': 'Missing authorization token'}), 401

    # Register blueprints
    from app.routes import bp
    from app.auth import auth_bp
    from app.messages import messages_bp
    from app.channels import channels_bp
    from app.products import products_bp
    from app.ai_settings import ai_settings_bp
    from app.automation import automation_bp
    from app.logs import logs_bp
    app.register_blueprint(bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(channels_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(ai_settings_bp)
    app.register_blueprint(automation_bp)
    app.register_blueprint(logs_bp)

    # Import models so Flask-Migrate can detect them
    with app.app_context():
        from app import models  # noqa: F401

    return app