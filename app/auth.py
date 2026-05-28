"""
app/auth.py
Authentication routes for login, signup, logout, and token verification.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from app import db
from app.models import AuthUser, AuditLog

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def get_client_ip():
    """Get the client's IP address from the request."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr


def log_audit(user_id, action, resource_type=None, resource_id=None, changes=None):
    """Log an audit event."""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=changes,
        ip_address=get_client_ip()
    )
    db.session.add(audit_log)
    db.session.commit()


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    Login endpoint.
    
    Request body:
    {
        "email": "user@company.com",
        "password": "password123"
    }
    
    Response:
    {
        "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        "user": {
            "id": 1,
            "email": "user@company.com",
            "full_name": "John Doe",
            "role": "admin",
            "status": "active"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400
        
        email = data.get('email').lower().strip()
        password = data.get('password')
        
        # Find user by email
        user = AuthUser.query.filter_by(email=email).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Check if user is active
        if user.status != 'active':
            return jsonify({'error': 'User account is not active'}), 403
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Create JWT token
        token = create_access_token(
            identity=user.id,
            additional_claims={'role': user.role, 'email': user.email},
            expires_delta=timedelta(hours=24)
        )
        
        # Log the login
        log_audit(user.id, 'login')
        
        return jsonify({
            'token': token,
            'user': user.to_dict()
        }), 200
    
    except Exception as e:
        print(f"Login error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Login failed: {str(e)}'}), 500


@auth_bp.route('/signup', methods=['POST'])
@jwt_required()
def signup():
    """
    Signup endpoint (admin only).
    Create a new internal user account.
    
    Request body:
    {
        "email": "newuser@company.com",
        "password": "password123",
        "full_name": "Jane Doe",
        "role": "agent"  # admin | agent | supervisor
    }
    
    Response:
    {
        "user": {
            "id": 2,
            "email": "newuser@company.com",
            "full_name": "Jane Doe",
            "role": "agent",
            "status": "active"
        }
    }
    """
    # Check if current user is admin
    current_user_id = get_jwt_identity()
    current_user = AuthUser.query.get(current_user_id)
    
    if not current_user or current_user.role != 'admin':
        return jsonify({'error': 'Only admins can create new users'}), 403
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['email', 'password', 'full_name', 'role']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing required fields: email, password, full_name, role'}), 400
    
    email = data.get('email').lower().strip()
    password = data.get('password')
    full_name = data.get('full_name').strip()
    role = data.get('role').lower()
    
    # Validate role
    if role not in ['admin', 'agent', 'supervisor']:
        return jsonify({'error': 'Invalid role. Must be: admin, agent, or supervisor'}), 400
    
    # Validate password strength (minimum 8 characters)
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters long'}), 400
    
    # Check if email already exists
    if AuthUser.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 409
    
    # Create new user
    new_user = AuthUser(
        email=email,
        full_name=full_name,
        role=role,
        status='active'
    )
    new_user.set_password(password)
    
    db.session.add(new_user)
    db.session.commit()
    
    # Log the user creation
    log_audit(
        current_user.id,
        'create_user',
        resource_type='user',
        resource_id=str(new_user.id),
        changes={'email': email, 'role': role}
    )
    
    return jsonify({
        'user': new_user.to_dict()
    }), 201


@auth_bp.route('/verify', methods=['GET'])
@jwt_required()
def verify():
    """
    Verify token and return current user info.
    
    Response:
    {
        "id": 1,
        "email": "user@company.com",
        "full_name": "John Doe",
        "role": "admin",
        "status": "active",
        "created_at": "2024-01-15T10:30:00",
        "last_login": "2024-01-20T14:45:00"
    }
    """
    try:
        user_id = get_jwt_identity()
        print(f"[VERIFY] Token verified, user_id: {user_id}")
        user = AuthUser.query.get(user_id)
        
        if not user:
            print(f"[VERIFY] User not found for id: {user_id}")
            return jsonify({'error': 'User not found'}), 404
        
        print(f"[VERIFY] User found: {user.email}")
        return jsonify(user.to_dict()), 200
    except Exception as e:
        print(f"[VERIFY] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout endpoint.
    In a production app, you would add the token to a blacklist here.
    
    Response:
    {
        "message": "Logged out successfully"
    }
    """
    user_id = get_jwt_identity()
    
    # Log the logout
    log_audit(user_id, 'logout')
    
    return jsonify({'message': 'Logged out successfully'}), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Get current user info (same as /verify but more explicit).
    
    Response:
    {
        "id": 1,
        "email": "user@company.com",
        "full_name": "John Doe",
        "role": "admin",
        "status": "active",
        "created_at": "2024-01-15T10:30:00",
        "last_login": "2024-01-20T14:45:00"
    }
    """
    user_id = get_jwt_identity()
    user = AuthUser.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify(user.to_dict()), 200


@auth_bp.route('/users', methods=['GET'])
@jwt_required()
def list_users():
    """
    List all users (admin only).
    
    Response:
    {
        "users": [
            {
                "id": 1,
                "email": "admin@company.com",
                "full_name": "Admin User",
                "role": "admin",
                "status": "active",
                "created_at": "2024-01-15T10:30:00",
                "last_login": "2024-01-20T14:45:00"
            },
            ...
        ]
    }
    """
    current_user_id = get_jwt_identity()
    current_user = AuthUser.query.get(current_user_id)
    
    if not current_user or current_user.role != 'admin':
        return jsonify({'error': 'Only admins can list users'}), 403
    
    users = AuthUser.query.all()
    
    return jsonify({
        'users': [user.to_dict() for user in users]
    }), 200


@auth_bp.route('/users/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user(user_id):
    """
    Get a specific user (admin only).
    
    Response:
    {
        "id": 1,
        "email": "user@company.com",
        "full_name": "John Doe",
        "role": "admin",
        "status": "active",
        "created_at": "2024-01-15T10:30:00",
        "last_login": "2024-01-20T14:45:00"
    }
    """
    current_user_id = get_jwt_identity()
    current_user = AuthUser.query.get(current_user_id)
    
    if not current_user or current_user.role != 'admin':
        return jsonify({'error': 'Only admins can view user details'}), 403
    
    user = AuthUser.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify(user.to_dict()), 200


@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_user(user_id):
    """
    Update a user (admin only).
    
    Request body:
    {
        "full_name": "Jane Doe",
        "role": "supervisor",
        "status": "active"
    }
    
    Response:
    {
        "user": { ... }
    }
    """
    current_user_id = get_jwt_identity()
    current_user = AuthUser.query.get(current_user_id)
    
    if not current_user or current_user.role != 'admin':
        return jsonify({'error': 'Only admins can update users'}), 403
    
    user = AuthUser.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    changes = {}
    
    # Update allowed fields
    if 'full_name' in data:
        user.full_name = data['full_name'].strip()
        changes['full_name'] = user.full_name
    
    if 'role' in data:
        new_role = data['role'].lower()
        if new_role not in ['admin', 'agent', 'supervisor']:
            return jsonify({'error': 'Invalid role'}), 400
        user.role = new_role
        changes['role'] = user.role
    
    if 'status' in data:
        new_status = data['status'].lower()
        if new_status not in ['active', 'inactive', 'suspended']:
            return jsonify({'error': 'Invalid status'}), 400
        user.status = new_status
        changes['status'] = user.status
    
    user.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Log the update
    log_audit(
        current_user.id,
        'update_user',
        resource_type='user',
        resource_id=str(user_id),
        changes=changes
    )
    
    return jsonify({
        'user': user.to_dict()
    }), 200


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    """
    Delete a user (admin only).
    
    Response:
    {
        "message": "User deleted successfully"
    }
    """
    current_user_id = get_jwt_identity()
    current_user = AuthUser.query.get(current_user_id)
    
    if not current_user or current_user.role != 'admin':
        return jsonify({'error': 'Only admins can delete users'}), 403
    
    # Prevent self-deletion
    if user_id == current_user_id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    user = AuthUser.query.get(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    db.session.delete(user)
    db.session.commit()
    
    # Log the deletion
    log_audit(
        current_user.id,
        'delete_user',
        resource_type='user',
        resource_id=str(user_id)
    )
    
    return jsonify({
        'message': 'User deleted successfully'
    }), 200


@auth_bp.route('/audit-logs', methods=['GET'])
@jwt_required()
def get_audit_logs():
    """
    Get audit logs (admin only).
    
    Query parameters:
    - user_id: Filter by user ID
    - action: Filter by action
    - limit: Number of logs to return (default: 100)
    - offset: Offset for pagination (default: 0)
    
    Response:
    {
        "logs": [
            {
                "id": 1,
                "user_id": 1,
                "action": "login",
                "resource_type": null,
                "resource_id": null,
                "changes": null,
                "ip_address": "192.168.1.1",
                "created_at": "2024-01-20T14:45:00"
            },
            ...
        ],
        "total": 150
    }
    """
    current_user_id = get_jwt_identity()
    current_user = AuthUser.query.get(current_user_id)
    
    if not current_user or current_user.role != 'admin':
        return jsonify({'error': 'Only admins can view audit logs'}), 403
    
    # Get query parameters
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', type=str)
    limit = request.args.get('limit', default=100, type=int)
    offset = request.args.get('offset', default=0, type=int)
    
    # Build query
    query = AuditLog.query
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    if action:
        query = query.filter_by(action=action)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset).all()
    
    return jsonify({
        'logs': [log.to_dict() for log in logs],
        'total': total,
        'limit': limit,
        'offset': offset
    }), 200
