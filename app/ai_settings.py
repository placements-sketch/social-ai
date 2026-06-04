"""
app/ai_settings.py
AI Settings — a single config row (id=1) controlling personalization:
tone, system prompt, personality sliders, response rules.

Note: model and max_tokens deliberately are NOT exposed here. They live
in config.py / .env because they're infrastructure decisions, not user
personalization knobs.

Endpoints (all JWT-protected, /api prefix):
  GET    /api/ai-settings        get the current config (auto-creates with
                                 defaults if missing)
  PUT    /api/ai-settings        update the current config (partial allowed)
  POST   /api/ai-settings/reset  reset all fields to defaults
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app import db
from app.models import AuthUser, AISettings
from app.auth import log_audit, current_user_id

ai_settings_bp = Blueprint('ai_settings', __name__, url_prefix='/api')


# Canonical defaults. Used when auto-creating the row, and by the reset endpoint.
VALID_TONES = {'friendly', 'luxury', 'gen_z', 'minimalist', 'bold_sales'}

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful customer support assistant for a Kenyan online "
    "fashion and beauty store. You respond in a warm, friendly tone, "
    "answer questions about products, pricing, stock, and delivery, "
    "and gently encourage customers to place an order when appropriate. "
    "Be concise and natural — like a knowledgeable shop assistant, not a robot."
)

DEFAULTS = {
    'tone': 'friendly',
    'system_prompt': DEFAULT_SYSTEM_PROMPT,
    'slider_formal': 40,
    'slider_length': 50,
    'slider_sales': 60,
    'response_rules': {
        'auto_greet': True,
        'mention_delivery_in_kenya': True,
        'use_emoji': True,
        'always_offer_alternatives_when_out_of_stock': True,
    },
}


def _get_or_create_settings() -> AISettings:
    """
    Get the singleton AISettings row (id=1), creating it with defaults if missing.
    """
    settings = AISettings.query.get(1)
    if settings is None:
        settings = AISettings(id=1, **DEFAULTS)
        db.session.add(settings)
        db.session.commit()
    return settings


@ai_settings_bp.route('/ai-settings', methods=['GET'])
@jwt_required()
def get_settings():
    """Return the current AI settings (auto-creates if missing)."""
    settings = _get_or_create_settings()
    return jsonify({'settings': settings.to_dict()}), 200


@ai_settings_bp.route('/ai-settings', methods=['PUT'])
@jwt_required()
def update_settings():
    """
    Update the AI settings. Partial updates allowed — only fields present
    in the body are touched.

    Body (all optional):
    {
      "tone": "friendly" | "luxury" | "gen_z" | "minimalist" | "bold_sales",
      "system_prompt": "...",
      "slider_formal": 0..100,
      "slider_length": 0..100,
      "slider_sales": 0..100,
      "response_rules": { ... }
    }
    """
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    settings = _get_or_create_settings()
    data = request.get_json(silent=True) or {}
    changes = {}

    if 'tone' in data:
        tone = (data['tone'] or '').lower()
        if tone not in VALID_TONES:
            return jsonify({
                'error': f'Invalid tone. Must be one of: {", ".join(sorted(VALID_TONES))}'
            }), 400
        settings.tone = tone
        changes['tone'] = tone

    if 'system_prompt' in data:
        prompt = (data['system_prompt'] or '').strip()
        if not prompt:
            return jsonify({'error': 'system_prompt cannot be empty'}), 400
        settings.system_prompt = prompt
        changes['system_prompt'] = '<updated>'  # don't dump the whole prompt to audit

    for slider in ('slider_formal', 'slider_length', 'slider_sales'):
        if slider in data:
            value = data[slider]
            if not isinstance(value, int) or value < 0 or value > 100:
                return jsonify({'error': f'{slider} must be an integer 0..100'}), 400
            setattr(settings, slider, value)
            changes[slider] = value

    if 'response_rules' in data:
        rules = data['response_rules']
        if rules is not None and not isinstance(rules, dict):
            return jsonify({'error': 'response_rules must be an object'}), 400
        settings.response_rules = rules
        changes['response_rules'] = '<updated>'

    if not changes:
        return jsonify({'error': 'No updatable fields provided'}), 400

    settings.updated_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        current_user.id,
        'update_ai_settings',
        resource_type='ai_settings',
        resource_id='1',
        changes=changes,
    )

    return jsonify({'settings': settings.to_dict()}), 200


@ai_settings_bp.route('/ai-settings/reset', methods=['POST'])
@jwt_required()
def reset_settings():
    """Reset all AI settings to the canonical defaults."""
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    settings = _get_or_create_settings()
    for key, value in DEFAULTS.items():
        setattr(settings, key, value)
    settings.updated_at = utcnow()
    db.session.commit()

    log_audit(
        current_user.id,
        'reset_ai_settings',
        resource_type='ai_settings',
        resource_id='1',
    )

    return jsonify({'settings': settings.to_dict()}), 200

