from flask import Flask
import os

app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'well-test-secret-key-2024-secure-long-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///well_test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'check_same_thread': False}
}

from extensions import db
db.init_app(app)

def register_blueprints():
    from routes.auth import auth_bp
    from routes.wells import wells_bp
    from routes.tests import tests_bp
    from routes.analytics import analytics_bp
    from routes.dashboard import dashboard_bp
    from routes.export import export_bp
    from routes.data import data_bp
    from routes.settings import settings_bp
    from routes.crude_export import crude_export_bp
    from routes.production import production_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(wells_bp)
    app.register_blueprint(tests_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(crude_export_bp)
    app.register_blueprint(production_bp)

register_blueprints()

@app.route('/gateway')
def gateway():
    from flask import render_template
    return render_template('gateway.html')

@app.errorhandler(404)
def page_not_found(e):
    from flask import render_template
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    from flask import render_template
    return render_template('500.html'), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from models import User, UserPermission, FEATURES
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            for f in FEATURES:
                perm = UserPermission(user_id=admin.id, feature=f[0], allowed=True)
                db.session.add(perm)
            db.session.commit()
            print("Created default admin user: admin / admin123")
            
        from backup_service import init_backup_service
        init_backup_service(app)
        
    app.run(debug=True, host='0.0.0.0', port=5000)