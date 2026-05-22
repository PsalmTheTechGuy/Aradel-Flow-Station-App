from flask import Blueprint, request, jsonify, current_app
from extensions import db
from models import User
import jwt
import datetime as dt
from functools import wraps

auth_bp = Blueprint('auth', __name__)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = User.query.get(data['sub'])
            if not current_user:
                print(f"Token valid but user {data.get('sub')} not found")
                return jsonify({'error': 'User not found'}), 401
        except Exception:
            return jsonify({'error': 'Token is invalid'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @token_required
    def decorated(current_user, *args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(current_user, *args, **kwargs)
    return decorated

@auth_bp.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Username and password required'}), 400
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    user = User(username=data['username'], role=data.get('role', 'operator'))
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered', 'user': user.to_dict()}), 201

@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Username and password required'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if not user or not user.check_password(data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = user.generate_token()
    return jsonify({
        'token': token, 
        'user': user.to_dict(include_permissions=True), 
        'expires_in': 3600
    }), 200

@auth_bp.route('/api/me', methods=['GET'])
def me():
    from flask import request
    token = None
    if 'Authorization' in request.headers:
        auth_header = request.headers['Authorization']
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
    if not token:
        return jsonify({'error': 'Token required'}), 401
    try:
        import jwt
        from flask import current_app
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(data['sub'])
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'user': user.to_dict(include_permissions=True)}), 200
    except:
        return jsonify({'error': 'Invalid token'}), 401

@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    return jsonify({'message': 'Logged out'}), 200