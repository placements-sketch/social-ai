"""
app/automation.py
Automation Rules — IF/THEN rules evaluated before AI generation.

Endpoints (all JWT-protected, /api prefix):
  GET    /api/automation-rules           list all rules (sorted by sort_order)
  GET    /api/automation-rules/<id>      single rule
  POST   /api/automation-rules           create a rule
  PATCH  /api/automation-rules/<id>      update (partial)
  DELETE /api/automation-rules/<id>      delete
  PATCH  /api/automation-rules/<id>/toggle    toggle enabled
  POST   /api/automation-rules/reorder   bulk reorder { "order": [id, id, ...] }
"""

from datetime import datetime, timezone
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app import db
from app.models import AuthUser, AutomationRule
from app.auth import log_audit, current_user_id

# UTC-aware datetime helper
def utc_now():
    """Return current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)

automation_bp = Blueprint('automation', __name__, url_prefix='/api')


# Known trigger and action types. Unknown types are rejected so a typo
# in the JSON doesn't silently produce a dead rule.
VALID_TRIGGER_TYPES = {'keyword', 'intent', 'shopify_stock', 'always', 'channel'}
VALID_ACTION_TYPES = {
    'include_price', 'reply_template', 'trigger_dm_flow',
    'human_escalate', 'ask_order_number', 'normal_reply', 'notify_agent',
}


def _validate_config(config, valid_types, label):
    """
    Accepts any JSON object; only the `type` field is checked. Returns
    (ok, error_message). If config is None/empty, treated as ok (permissive).
    """
    if config is None:
        return True, None
    if not isinstance(config, dict):
        return False, f"{label} must be a JSON object"
    if 'type' in config and config['type'] not in valid_types:
        return False, (f"Unknown {label}.type '{config['type']}'. "
                       f"Valid types: {', '.join(sorted(valid_types))}")
    return True, None


@automation_bp.route('/automation-rules', methods=['GET'])
@jwt_required()
def list_rules():
    """List all rules in execution order."""
    enabled_only = request.args.get('enabled_only', type=str)
    query = AutomationRule.query
    if enabled_only and enabled_only.lower() in ('1', 'true', 'yes'):
        query = query.filter_by(enabled=True)
    rules = query.order_by(AutomationRule.sort_order.asc(), AutomationRule.id.asc()).all()
    return jsonify({
        'rules': [r.to_dict() for r in rules],
        'total': len(rules),
    }), 200


@automation_bp.route('/automation-rules/<int:rule_id>', methods=['GET'])
@jwt_required()
def get_rule(rule_id):
    rule = AutomationRule.query.get(rule_id)
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404
    return jsonify({'rule': rule.to_dict()}), 200


@automation_bp.route('/automation-rules', methods=['POST'])
@jwt_required()
def create_rule():
    """
    Create a rule.

    Body:
    {
      "name": "...",                    required
      "trigger": "...",                 required (human-readable description)
      "action": "...",                  required (human-readable description)
      "trigger_config": { ... },        optional (machine-readable)
      "action_config":  { ... },        optional (machine-readable)
      "enabled": true,                  optional, default true
      "sort_order": 0                   optional, default = last
    }
    """
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    trigger = (data.get('trigger') or '').strip()
    action = (data.get('action') or '').strip()

    missing = [f for f, v in [('name', name), ('trigger', trigger), ('action', action)] if not v]
    if missing:
        return jsonify({'error': f"Missing required fields: {', '.join(missing)}"}), 400

    trigger_config = data.get('trigger_config')
    action_config = data.get('action_config')

    ok, err = _validate_config(trigger_config, VALID_TRIGGER_TYPES, 'trigger_config')
    if not ok:
        return jsonify({'error': err}), 400
    ok, err = _validate_config(action_config, VALID_ACTION_TYPES, 'action_config')
    if not ok:
        return jsonify({'error': err}), 400

    # Default sort_order = last position
    if 'sort_order' in data and isinstance(data['sort_order'], int):
        sort_order = data['sort_order']
    else:
        max_order = db.session.query(db.func.max(AutomationRule.sort_order)).scalar()
        sort_order = (max_order or 0) + 1

    rule = AutomationRule(
        name=name,
        trigger=trigger,
        action=action,
        trigger_config=trigger_config,
        action_config=action_config,
        enabled=bool(data.get('enabled', True)),
        sort_order=sort_order,
    )
    db.session.add(rule)
    db.session.commit()

    log_audit(
        current_user.id, 'create_automation_rule',
        resource_type='automation_rule', resource_id=str(rule.id),
        changes={'name': name},
    )

    return jsonify({'rule': rule.to_dict()}), 201


@automation_bp.route('/automation-rules/<int:rule_id>', methods=['PATCH'])
@jwt_required()
def update_rule(rule_id):
    """Partial update."""
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    rule = AutomationRule.query.get(rule_id)
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    data = request.get_json(silent=True) or {}
    changes = {}

    if 'name' in data:
        name = (data['name'] or '').strip()
        if not name:
            return jsonify({'error': 'name cannot be empty'}), 400
        rule.name = name
        changes['name'] = name

    if 'trigger' in data:
        trig = (data['trigger'] or '').strip()
        if not trig:
            return jsonify({'error': 'trigger cannot be empty'}), 400
        rule.trigger = trig
        changes['trigger'] = '<updated>'

    if 'action' in data:
        act = (data['action'] or '').strip()
        if not act:
            return jsonify({'error': 'action cannot be empty'}), 400
        rule.action = act
        changes['action'] = '<updated>'

    if 'trigger_config' in data:
        ok, err = _validate_config(data['trigger_config'], VALID_TRIGGER_TYPES, 'trigger_config')
        if not ok:
            return jsonify({'error': err}), 400
        rule.trigger_config = data['trigger_config']
        changes['trigger_config'] = '<updated>'

    if 'action_config' in data:
        ok, err = _validate_config(data['action_config'], VALID_ACTION_TYPES, 'action_config')
        if not ok:
            return jsonify({'error': err}), 400
        rule.action_config = data['action_config']
        changes['action_config'] = '<updated>'

    if 'enabled' in data:
        rule.enabled = bool(data['enabled'])
        changes['enabled'] = rule.enabled

    if 'sort_order' in data and isinstance(data['sort_order'], int):
        rule.sort_order = data['sort_order']
        changes['sort_order'] = rule.sort_order

    if not changes:
        return jsonify({'error': 'No updatable fields provided'}), 400

    rule.updated_at = utc_now()
    db.session.commit()

    log_audit(
        current_user.id, 'update_automation_rule',
        resource_type='automation_rule', resource_id=str(rule.id),
        changes=changes,
    )

    return jsonify({'rule': rule.to_dict()}), 200


@automation_bp.route('/automation-rules/<int:rule_id>', methods=['DELETE'])
@jwt_required()
def delete_rule(rule_id):
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    rule = AutomationRule.query.get(rule_id)
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    name = rule.name
    db.session.delete(rule)
    db.session.commit()

    log_audit(
        current_user.id, 'delete_automation_rule',
        resource_type='automation_rule', resource_id=str(rule_id),
        changes={'name': name},
    )

    return jsonify({'message': 'Rule deleted'}), 200


@automation_bp.route('/automation-rules/<int:rule_id>/toggle', methods=['PATCH'])
@jwt_required()
def toggle_rule(rule_id):
    """Convenience: flip enabled without sending its current value."""
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    rule = AutomationRule.query.get(rule_id)
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    rule.enabled = not rule.enabled
    rule.updated_at = utc_now()
    db.session.commit()

    log_audit(
        current_user.id, 'toggle_automation_rule',
        resource_type='automation_rule', resource_id=str(rule.id),
        changes={'enabled': rule.enabled},
    )

    return jsonify({'rule': rule.to_dict()}), 200


@automation_bp.route('/automation-rules/reorder', methods=['POST'])
@jwt_required()
def reorder_rules():
    """
    Atomic bulk reorder. The body's `order` array is the new sequence of
    rule IDs from top to bottom. Sort_order is re-normalised to 1..N.

    Body:
    { "order": [3, 1, 5, 2, 4, 6] }

    Validates that the array contains exactly the set of all existing rule
    IDs — no missing, no extras. Either everything updates or nothing does.
    """
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    data = request.get_json(silent=True) or {}
    order = data.get('order')
    if not isinstance(order, list) or not all(isinstance(i, int) for i in order):
        return jsonify({'error': 'order must be an array of integer rule IDs'}), 400

    existing_ids = {r.id for r in AutomationRule.query.all()}
    submitted_ids = set(order)

    if submitted_ids != existing_ids:
        missing = existing_ids - submitted_ids
        extras = submitted_ids - existing_ids
        return jsonify({
            'error': 'order must contain every existing rule id exactly once',
            'missing': sorted(missing),
            'extras': sorted(extras),
            'duplicates': len(order) != len(submitted_ids),
        }), 400

    # Re-normalise: position 1..N in the submitted order
    for position, rid in enumerate(order, start=1):
        rule = AutomationRule.query.get(rid)
        rule.sort_order = position
        rule.updated_at = utc_now()

    db.session.commit()

    log_audit(
        current_user.id, 'reorder_automation_rules',
        resource_type='automation_rules', resource_id=None,
        changes={'order': order},
    )

    rules = AutomationRule.query.order_by(AutomationRule.sort_order.asc()).all()
    return jsonify({
        'rules': [r.to_dict() for r in rules],
        'total': len(rules),
    }), 200

