"""
app/health.py
Lightweight system-health signal for the top-bar status dot.
'operational' unless there are error logs or failed sync jobs in the last hour.
"""
from datetime import datetime, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.models import Log, SyncJob

health_bp = Blueprint('health', __name__, url_prefix='/api')


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

    if errors > 0 or failed:
        status = 'critical'
    elif warnings > 0:
        status = 'degraded'
    else:
        status = 'operational'

    return jsonify({
        'status':      status,
        'errors':      errors,
        'warnings':    warnings,
        'failed_jobs': len(failed),
        'issues':      issues,
        'checked_at':  datetime.utcnow().isoformat(),
    }), 200