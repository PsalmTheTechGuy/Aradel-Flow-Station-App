from flask import Blueprint, request, jsonify, render_template, session, abort
from extensions import db
from models import User, UserPermission, FEATURES
import jwt
import os
from datetime import datetime
from flask import send_file

settings_bp = Blueprint('settings', __name__)

from .auth import token_required, admin_required

@settings_bp.route('/settings')
def settings():
    users = User.query.all()
    features = FEATURES
    user_permissions = {}
    for u in users:
        perms = {}
        for f in features:
            perm = UserPermission.query.filter_by(user_id=u.id, feature=f[0]).first()
            perms[f[0]] = perm.allowed if perm else True
        user_permissions[u.id] = perms
    return render_template('settings.html', users=users, features=features, user_permissions=user_permissions)

@settings_bp.route('/api/users', methods=['GET'])
@token_required
def get_users(current_user):
    users = User.query.all()
    return jsonify([u.to_dict(include_permissions=True) for u in users]), 200

@settings_bp.route('/api/users', methods=['POST'])
@admin_required
def create_user(current_user):
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'error': 'Username and password required'}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400
    
    user = User(username=data['username'], role=data.get('role', 'operator'))
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    
    for feature in FEATURES:
        allowed = data.get(f'perm_{feature[0]}', True)
        perm = UserPermission(user_id=user.id, feature=feature[0], allowed=allowed)
        db.session.add(perm)
    db.session.commit()
    
    return jsonify({'message': 'User created', 'user': user.to_dict(include_permissions=True)}), 201

@settings_bp.route('/api/users/<int:id>', methods=['PUT'])
@admin_required
def update_user(current_user, id):
    user = User.query.get_or_404(id)
    data = request.get_json()
    
    if 'role' in data:
        user.role = data['role']
    
    if 'password' in data and data['password']:
        user.set_password(data['password'])
    
    for feature in FEATURES:
        perm_key = f'perm_{feature[0]}'
        if perm_key in data:
            perm = UserPermission.query.filter_by(user_id=id, feature=feature[0]).first()
            if perm:
                perm.allowed = data[perm_key]
            else:
                perm = UserPermission(user_id=id, feature=feature[0], allowed=data[perm_key])
                db.session.add(perm)
    
    db.session.commit()
    return jsonify({'message': 'User updated', 'user': user.to_dict(include_permissions=True)}), 200

@settings_bp.route('/api/users/<int:id>', methods=['DELETE'])
@admin_required
def delete_user(current_user, id):
    if id == current_user.id:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    user = User.query.get_or_404(id)
    if user.username == 'admin':
        return jsonify({'error': 'Cannot delete admin user'}), 400
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted'}), 200

@settings_bp.route('/api/settings/reset-crude-export', methods=['POST'])
@admin_required
def reset_crude_export(current_user):
    from models import CrudeExport
    try:
        # Use bulk delete with synchronize_session=False for robustness
        num_deleted = db.session.query(CrudeExport).delete(synchronize_session=False)
        db.session.commit()
        response = jsonify({'message': f'Deleted {num_deleted} crude export records successfully.'})
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response, 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/reset-welltest', methods=['POST'])
@admin_required
def reset_welltest(current_user):
    from models import Well, WellTest, TestReading
    try:
        # SQLite doesn't enforce foreign key cascades by default, so we must delete children first
        db.session.query(TestReading).delete(synchronize_session=False)
        db.session.query(WellTest).delete(synchronize_session=False)
        num_deleted = db.session.query(Well).delete(synchronize_session=False)
        db.session.commit()
        response = jsonify({'message': f'Deleted {num_deleted} wells and all associated tests successfully.'})
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response, 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/features')
@token_required
def get_features(current_user):
    return jsonify(FEATURES), 200

@settings_bp.route('/settings/backup')
def backup_page():
    from flask import current_app
    instance_path = current_app.instance_path
    if not os.path.exists(instance_path):
        instance_path = os.path.join(current_app.root_path, 'instance')
        
    db_path = os.path.join(instance_path, 'well_test.db')
    
    # Get DB stats
    db_size = 0
    last_modified = "Never"
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path) / (1024 * 1024) # MB
        last_modified = datetime.fromtimestamp(os.path.getmtime(db_path)).strftime('%Y-%m-%d %H:%M:%S')
        
    # Get recent automated backups
    app_root = os.path.dirname(instance_path)
    if app_root.endswith('well_test_system'):
        backup_dir = os.path.join(app_root, 'backups')
    else:
        backup_dir = os.path.join(os.path.dirname(instance_path), 'backups')
        
    backups = []
    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            if f.endswith('.db'):
                filepath = os.path.join(backup_dir, f)
                size = os.path.getsize(filepath) / (1024 * 1024)
                date = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime('%Y-%m-%d %H:%M:%S')
                backups.append({'name': f, 'size': size, 'date': date})
    backups.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('settings/backup.html', db_size=db_size, last_modified=last_modified, backups=backups)

@settings_bp.route('/settings/backup/download')
def download_backup():
    # Verify token from query parameter for direct downloads
    token = request.args.get('token')
    if not token:
        abort(401, "Token required for download.")
        
    try:
        from flask import current_app
        import jwt
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(data['sub'])
        if not user or user.role != 'admin':
            abort(403, "Admin access required.")
    except Exception:
        abort(401, "Invalid token.")
        
    instance_path = current_app.instance_path
    if not os.path.exists(instance_path):
        instance_path = os.path.join(current_app.root_path, 'instance')
        
    db_path = os.path.join(instance_path, 'well_test.db')
    
    if not os.path.exists(db_path):
        abort(404, "Database file not found.")
        
    timestamp = datetime.now().strftime('%Y-%m-%d')
    download_name = f"ExportTracker_Backup_{timestamp}.db"
    
    return send_file(db_path, as_attachment=True, download_name=download_name)