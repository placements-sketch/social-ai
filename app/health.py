"""
app/health.py
Lightweight system-health signal for the top-bar status dot.
'operational' unless there are error logs or failed sync jobs in the last hour.
"""
import os
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.models import Log, SyncJob

health_bp = Blueprint('health', __name__, url_prefix='/api')

# How many error logs in the last hour before the bar goes red. Below this it
# shows amber ("running with warnings") rather than crying outage over one
# transient failure.
CRITICAL_ERROR_COUNT = int(os.getenv('HEALTH_CRITICAL_ERRORS', '5'))


@health_bp.route('/health', methods=['GET'])
@jwt_required()
def health():
    cutoff = datetime.utcnow() - timedelta(hours=1)

    # log_event is called with BOTH 'warn' and 'warning' across the codebase,
    # so match both — the old `== 'warning'` check silently missed half of them.
    ERROR_LEVELS = ('error', 'critical')
    WARN_LEVELS = ('warning', 'warn')

    errors = Log.query.filter(
        Log.level.in_(ERROR_LEVELS), Log.created_at >= cutoff).count()
    warnings = Log.query.filter(
        Log.level.in_(WARN_LEVELS), Log.created_at >= cutoff).count()
    failed = SyncJob.query.filter(
        SyncJob.status == 'failed', SyncJob.finished_at >= cutoff).all()

    # The actual issues, not just counts — a bare "System issues detected"
    # tells nobody what to go and fix.
    recent = (Log.query
              .filter(Log.level.in_(ERROR_LEVELS + WARN_LEVELS))
              .filter(Log.created_at >= cutoff)
              .order_by(Log.created_at.desc())
              .limit(8).all())

    issues = [{
        'level':   l.level,
        'source':  l.source,
        'message': (l.message or '')[:300],
        'at':      l.created_at.isoformat() if l.created_at else None,
    } for l in recent]

    for j in failed:
        issues.append({
            'level':   'error',
            'source':  f'sync.{j.kind}',
            'message': (j.error or 'Sync job failed')[:300],
            'at':      j.finished_at.isoformat() if j.finished_at else None,
        })

    # A single stray error used to flip the whole bar to red "System issues
    # detected". In a live system something errors most hours, so the light was
    # permanently red and stopped meaning anything — the one job a status
    # indicator has. A failed sync job is still instantly critical (it's a
    # real, actionable outage); loose error logs have to actually pile up.
    if failed or errors >= CRITICAL_ERROR_COUNT:
        status = 'critical'
    elif errors > 0 or warnings > 0:
        status = 'degraded'
    else:
        status = 'operational'

    # The status dot is for everyone. The issue TEXT is not: it's raw log
    # output that includes things like database hostnames and IPs, which an
    # agent can neither act on nor should be handed. Matches the access model
    # on /api/alerts.
    from app.models import AuthUser
    from app.auth import current_user_id
    viewer = AuthUser.query.get(current_user_id())
    can_see_detail = bool(viewer and viewer.role in {'admin', 'supervisor'})

    # The business timezone the Dashboard reports in. The top bar clock used
    # the browser's zone, so a user abroad saw their own local time next to
    # figures bucketed by Nairobi days.
    tz_name = 'Africa/Nairobi'
    try:
        from app.settings import get_section
        tz_name = (get_section('business').get('timezone') or tz_name).strip()
    except Exception:
        pass

    return jsonify({
        'status':      status,
        'errors':      errors,
        'warnings':    warnings,
        'failed_jobs': len(failed),
        'issues':      issues if can_see_detail else [],
        'detail_visible': can_see_detail,
        'timezone':    tz_name,
        'checked_at':  datetime.utcnow().isoformat(),
    }), 200