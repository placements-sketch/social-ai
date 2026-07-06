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

    errors = Log.query.filter(Log.level == 'error', Log.created_at >= cutoff).count()
    warnings = Log.query.filter(Log.level == 'warning', Log.created_at >= cutoff).count()
    failed_jobs = SyncJob.query.filter(
        SyncJob.status == 'failed', SyncJob.finished_at >= cutoff
    ).count()

    if errors > 0 or failed_jobs > 0:
        status = 'critical'
    elif warnings > 0:
        status = 'degraded'
    else:
        status = 'operational'

    return jsonify({
        'status': status,
        'errors': errors,
        'warnings': warnings,
        'failed_jobs': failed_jobs,
        'checked_at': datetime.utcnow().isoformat(),
    }), 200