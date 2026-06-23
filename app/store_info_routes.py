"""
app/store_info_routes.py
Endpoints for the store-info cache (locations, shipping zones, discounts).
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from app.models import AuthUser, StoreInfoCache
from app.auth import current_user_id
from app.sync_jobs import start_background_job, get_latest_job
from app.store_info import sync_locations_now

store_info_bp = Blueprint('store_info', __name__, url_prefix='/api')


@store_info_bp.route('/store-info/status', methods=['GET'])
@jwt_required()
def store_info_status():
    """What's currently in the cache, and any in-flight sync."""
    rows = StoreInfoCache.query.all()
    return jsonify({
        'cache': [
            {
                'kind': r.kind,
                'count': len(r.data) if isinstance(r.data, list) else 0,
                'updated_at': r.updated_at.isoformat() if r.updated_at else None,
            } for r in rows
        ],
        'current_job': (get_latest_job('store_info').to_dict()
                        if get_latest_job('store_info') else None),
    }), 200


@store_info_bp.route('/store-info/sync', methods=['POST'])
@jwt_required()
def store_info_sync():
    """
    Sync store-wide info from Shopify into the cache.
    Currently syncs: locations. (Shipping zones + discounts coming next.)
    """
    current_user = AuthUser.query.get(current_user_id())
    if current_user is None:
        return jsonify({'error': 'User not found'}), 404
    if current_user.role != 'admin':
        return jsonify({'error': 'Only admins can sync store info'}), 403

    def do_sync(job):
        job.progress = "Fetching locations from Shopify..."
        from app import db
        db.session.commit()

        result = sync_locations_now()

        return result

    job, started = start_background_job(
        kind='store_info_sync',
        work_fn=do_sync,
        user_id=current_user.id,
    )
    if not started:
        return jsonify({
            'job_id': job.id,
            'status': job.status,
            'message': 'A store info sync is already running.',
        }), 409

    return jsonify({'job_id': job.id, 'status': job.status}), 202