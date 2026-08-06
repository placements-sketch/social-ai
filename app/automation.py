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

automation_bp = Blueprint('automation', __name__, url_prefix='/api')



# ── Authorisation ────────────────────────────────────────────────────────────
# Every route in this file previously carried @jwt_required() and nothing else.
# The sidebar shows this section to admins only, but that is the interface — the
# endpoints were reachable by anyone with a valid token, including an agent.
#
# What that allowed, concretely: rewriting the system prompt that governs every
# AI reply to every customer, changing the brand tone and personality, resetting
# the whole configuration, and creating, editing, reordering, toggling or
# deleting automation rules. The handlers even call notify_admins() afterwards —
# the code expected only admins to reach them while permitting everybody.
#
# Defined once here rather than repeated per route, so a route added later
# cannot quietly skip the check by being written without it.

def _require_role(*roles):
    """Return (user, None) when the caller holds one of `roles`, else (None, response)."""
    user = AuthUser.query.get(current_user_id())
    if not user:
        return None, (jsonify({'error': 'User not found'}), 404)
    if user.role not in roles:
        return None, (jsonify({'error': 'Forbidden'}), 403)
    return user, None


def _require_admin():
    """Changing how the assistant behaves is an admin decision."""
    return _require_role('admin')


def _require_viewer():
    """Reading the configuration. Supervisors oversee agents, so they may look."""
    return _require_role('admin', 'supervisor')


# Known trigger and action types. Unknown types are rejected so a typo
# in the JSON doesn't silently produce a dead rule.
VALID_TRIGGER_TYPES = {'keyword', 'intent', 'shopify_stock', 'always', 'channel'}
VALID_ACTION_TYPES = {
    'include_price', 'reply_template', 'trigger_dm_flow',
    'human_escalate', 'ask_order_number', 'normal_reply', 'notify_agent',
}


# ── What is actually wired up ────────────────────────────────────────────────
# Being a *valid* type and being a type that *does something* were two different
# things, and only the first was checked. The list above rejects typos "so a typo
# doesn't silently produce a dead rule" — but five of the seven accepted action
# types had no executor anywhere, so well-formed rules sat in the UI marked
# Enabled and never ran. Of the five rules in this database, three could not fire
# through any code path at all.
#
# These two sets are the honest answer, kept next to the validator so they cannot
# drift from it. A type here means: some code reads it and changes behaviour.
#
#   reply_template   -> services.py::_run_automation_action sends the canned reply
#   ask_order_number -> asks for the name + email the order lookup needs
#   trigger_dm_flow  -> AI's answer goes to the DM, teaser goes under the post
#                       (services.py Step 3.6 defers, Step 6 routes)
#   include_price    -> directive on context_data; generator.py states the price
#   human_escalate   }
#   notify_agent     }- handoff.py::_match_automation_rule routes to a human
IMPLEMENTED_ACTION_TYPES = {
    'reply_template', 'human_escalate', 'notify_agent', 'ask_order_number',
    'trigger_dm_flow', 'include_price',
}
# shopify_stock is evaluated in a second pass at Step 4.6, after the Shopify
# fetch and the live stock refresh — see services.py::_match_automation_actions.
IMPLEMENTED_TRIGGER_TYPES = {'keyword', 'intent', 'always', 'channel', 'shopify_stock'}

# Triggers judged in the second pass, because they need the matched product.
# Defined here and imported by services.py so the split has one definition —
# a rule can only shadow another rule in the SAME pass.
STOCK_TRIGGER_TYPES = {'shopify_stock'}

# Actions that route a conversation to a person. These are executed by
# handoff.py at Step 3.5, which scans every enabled rule independently — it is
# NOT first-match-wins — so a catch-all rule sitting above one of these does not
# stop it firing. Imported by handoff.py so the list has one definition.
ESCALATION_ACTION_TYPES = {'human_escalate', 'notify_agent', 'ask_order_number'}

# ── Terminal vs directive ────────────────────────────────────────────────────
# "First matching rule wins" is right for actions that ANSWER the customer —
# you cannot send two canned replies to one message, so the first one to match
# has to win and the rest must not fire.
#
# It is wrong for actions that only SHAPE the reply the assistant is going to
# write anyway. include_price adds an instruction to the prompt; it sends
# nothing. Treating it as terminal meant an include_price rule sitting near the
# top silently switched off every rule beneath it — so a customer asking about a
# sold-out item would get the price mentioned but never the out-of-stock reply.
#
# Directive actions therefore accumulate and evaluation CONTINUES. Terminal
# actions stop it. normal_reply is terminal on purpose: it is the explicit
# "stop here and let the assistant answer" exception.
DIRECTIVE_ACTION_TYPES = {'include_price'}


def is_terminal_action(action_type) -> bool:
    """True if matching this action stops any further rule from being applied."""
    return action_type not in DIRECTIVE_ACTION_TYPES

# `normal_reply` runs, but by design produces no visible action: rules are
# first-match-wins, so its purpose is to MATCH and thereby stop any later rule
# from applying — an exception carved out above a broad canned-reply rule.
NO_OP_ACTION_TYPES = {'normal_reply'}


def _shadowed_by(rule, preceding) -> object | None:
    """
    The first earlier rule that makes this one unreachable, or None.

    Rules are first-match-wins, so an enabled rule with an `always` trigger
    swallows everything below it in the same pass — the rules underneath are
    unreachable code. This is real: the "After Hours" rule here triggers on
    `always` and sat above "Comment → DM", so that rule could never run no
    matter how it was configured.

    Two things stop a rule shadowing another: a different pass (stock rules are
    evaluated separately, so an `always` rule cannot shadow a shopify_stock
    one), and a narrower channel scope than the rule below it.
    """
    tc = rule.trigger_config or {}
    mine_stock = tc.get('type') in STOCK_TRIGGER_TYPES
    my_channels = set(tc.get('channels') or [])

    for prev in preceding:
        if not prev.enabled:
            continue
        ptc = prev.trigger_config or {}
        if (ptc.get('type') in STOCK_TRIGGER_TYPES) != mine_stock:
            continue                       # different pass — cannot shadow
        if ptc.get('type') != 'always':
            continue                       # only a catch-all shadows everything
        if not is_terminal_action((prev.action_config or {}).get('type')):
            continue                       # a directive doesn't stop evaluation
        prev_channels = set(ptc.get('channels') or [])
        if prev_channels:
            # A scoped catch-all only shadows rules confined to those channels.
            if not my_channels or not my_channels.issubset(prev_channels):
                continue
        return prev
    return None


def rule_execution_status(rule, preceding=()) -> dict:
    """
    Can this rule ever fire? Returned with every rule so the UI can say so
    instead of showing a green Enabled pill on a rule that does nothing.

    `preceding` is the enabled rules ordered above this one, needed to spot
    rules that are unreachable rather than merely unimplemented.
    """
    tc = rule.trigger_config or {}
    ac = rule.action_config or {}
    ttype, atype = tc.get('type'), ac.get('type')

    # Escalating actions run in handoff.py's own pass, which is not
    # first-match-wins, so being shadowed here doesn't stop them reaching a
    # human. Warning about them would be a false alarm.
    shadower = None if atype in ESCALATION_ACTION_TYPES else _shadowed_by(rule, preceding)
    if shadower is not None:
        return {'runnable': False, 'no_op': False,
                'reason': f'Unreachable — "{shadower.name}" above it triggers on '
                          f'every message, and the first matching rule wins. '
                          f'Move this rule above it, or narrow that one.'}

    if atype in NO_OP_ACTION_TYPES:
        return {'runnable': True, 'no_op': True,
                'reason': 'Sends nothing itself. Because the first matching rule '
                          'wins, it stops any rule below it from firing and lets '
                          'the assistant reply normally.'}

    if atype and atype not in IMPLEMENTED_ACTION_TYPES:
        return {'runnable': False, 'no_op': False,
                'reason': f'The action "{atype}" is not implemented yet, so this '
                          f'rule never runs.'}

    if ttype and ttype not in IMPLEMENTED_TRIGGER_TYPES:
        return {'runnable': False, 'no_op': False,
                'reason': f'The trigger "{ttype}" is not evaluated yet, so this '
                          f'rule never runs.'}

    if atype == 'reply_template' and not ac.get('template'):
        return {'runnable': False, 'no_op': False,
                'reason': 'A template reply with no template text.'}

    return {'runnable': True, 'no_op': False, 'reason': None}


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
    _user, _err = _require_viewer()
    if _err:
        return _err
    enabled_only = request.args.get('enabled_only', type=str)
    query = AutomationRule.query
    if enabled_only and enabled_only.lower() in ('1', 'true', 'yes'):
        query = query.filter_by(enabled=True)
    rules = query.order_by(AutomationRule.sort_order.asc(), AutomationRule.id.asc()).all()
    return jsonify({
        # `execution` rides along with every rule so the list can show which
        # ones actually do something. Enabled and runnable are not the same.
        # Each rule is judged against the ones ordered above it, so an
        # unreachable rule reports as unreachable rather than as fine.
        'rules': [{**r.to_dict(), 'execution': rule_execution_status(r, rules[:i])}
                  for i, r in enumerate(rules)],
        'total': len(rules),
    }), 200


@automation_bp.route('/automation-rules/<int:rule_id>', methods=['GET'])
@jwt_required()
def get_rule(rule_id):
    _user, _err = _require_viewer()
    if _err:
        return _err
    rule = AutomationRule.query.get(rule_id)
    # Captured before the delete, so the audit entry can rebuild it.
    snapshot = {
        c.name: (getattr(rule, c.name).isoformat()
                 if hasattr(getattr(rule, c.name), 'isoformat')
                 else getattr(rule, c.name))
        for c in AutomationRule.__table__.columns
    } if rule else None
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
    _user, _err = _require_admin()
    if _err:
        return _err
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
    db.session.flush()  # get rule.id

    from app.notifications import notify_admins
    notify_admins(
        type_='automation_rule_created',
        title=f"New automation rule: {name}",
        body=f"{current_user.full_name} added a rule",
        severity='info',
        resource_type='automation_rule',
        resource_id=rule.id,
        actor_id=current_user.id,
    )

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
    _user, _err = _require_admin()
    if _err:
        return _err
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

    rule.updated_at = datetime.utcnow()

    from app.notifications import notify_admins
    field_summary = ', '.join(sorted(changes.keys()))
    notify_admins(
        type_='automation_rule_updated',
        title=f"Rule updated: {rule.name}",
        body=f"{current_user.full_name} changed {field_summary}",
        severity='info',
        resource_type='automation_rule',
        resource_id=rule.id,
        actor_id=current_user.id,
        coalesce=True,
    )

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
    _user, _err = _require_admin()
    if _err:
        return _err
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    rule = AutomationRule.query.get(rule_id)
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    name = rule.name
    db.session.delete(rule)

    from app.notifications import notify_admins
    notify_admins(
        type_='automation_rule_deleted',
        title=f"Rule deleted: {name}",
        body=f"{current_user.full_name} removed an automation rule",
        severity='warning',
        resource_type='automation_rule',
        resource_id=rule_id,
        actor_id=current_user.id,
    )

    db.session.commit()

    # Snapshot the WHOLE rule, not just its name.
    #
    # This recorded {'name': ...} only, which is enough to know something was
    # deleted and useless for putting it back. A rule's value is its trigger,
    # its action and their configs — the name is a label. Discovered the hard
    # way: a rule was deleted during testing and the audit trail could say what
    # it was called and nothing about what it did.
    #
    # An audit entry for a destructive action should be sufficient to
    # reconstruct what was destroyed. Otherwise it records that history was
    # lost without preserving any of it.
    log_audit(
        current_user.id, 'delete_automation_rule',
        resource_type='automation_rule', resource_id=str(rule_id),
        changes={'deleted_rule': snapshot},
    )

    return jsonify({'message': 'Rule deleted'}), 200


@automation_bp.route('/automation-rules/<int:rule_id>/toggle', methods=['PATCH'])
@jwt_required()
def toggle_rule(rule_id):
    """Convenience: flip enabled without sending its current value."""
    _user, _err = _require_admin()
    if _err:
        return _err
    current_user = AuthUser.query.get(current_user_id())
    if not current_user:
        return jsonify({'error': 'User not found'}), 404

    rule = AutomationRule.query.get(rule_id)
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404

    rule.enabled = not rule.enabled
    rule.updated_at = datetime.utcnow()

    from app.notifications import notify_admins
    state = 'enabled' if rule.enabled else 'disabled'
    notify_admins(
        type_='automation_rule_toggled',
        title=f"Rule {state}: {rule.name}",
        body=f"{current_user.full_name} turned this rule {state}",
        severity='info',
        resource_type='automation_rule',
        resource_id=rule.id,
        actor_id=current_user.id,
        coalesce=True,
    )

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
    _user, _err = _require_admin()
    if _err:
        return _err
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
        rule.updated_at = datetime.utcnow()

    db.session.commit()

    log_audit(
        current_user.id, 'reorder_automation_rules',
        resource_type='automation_rules', resource_id=None,
        changes={'order': order},
    )

    rules = AutomationRule.query.order_by(AutomationRule.sort_order.asc()).all()
    return jsonify({
        # `execution` rides along with every rule so the list can show which
        # ones actually do something. Enabled and runnable are not the same.
        # Each rule is judged against the ones ordered above it, so an
        # unreachable rule reports as unreachable rather than as fine.
        'rules': [{**r.to_dict(), 'execution': rule_execution_status(r, rules[:i])}
                  for i, r in enumerate(rules)],
        'total': len(rules),
    }), 200

