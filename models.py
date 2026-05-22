from datetime import datetime
import jwt
import datetime as dt
import hashlib

# Import db from extensions instead of creating new instance
from extensions import db

class Well(db.Model):
    __tablename__ = 'wells'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    location = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tests = db.relationship('WellTest', backref='well', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'location': self.location,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class WellTest(db.Model):
    __tablename__ = 'well_tests'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.String(100), unique=True, nullable=False)
    well_id = db.Column(db.Integer, db.ForeignKey('wells.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    remarks = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')
    avg_gross_rate = db.Column(db.Float)
    avg_bsw = db.Column(db.Float)
    net_prod = db.Column(db.Float)
    gross_bsw = db.Column(db.Float)
    
    readings = db.relationship('TestReading', backref='well_test', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'test_id': self.test_id,
            'well_id': self.well_id,
            'well_name': self.well.name if self.well else None,
            'date': self.date.isoformat() if self.date else None,
            'remarks': self.remarks,
            'status': self.status,
            'readings_count': self.readings.count(),
            'avg_gross_rate': self.avg_gross_rate,
            'avg_bsw': self.avg_bsw,
            'net_prod': self.net_prod,
            'gross_bsw': self.gross_bsw
        }

class TestReading(db.Model):
    __tablename__ = 'test_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('well_tests.id'), nullable=False)
    time = db.Column(db.Time, nullable=False)
    bean_size = db.Column(db.Float)
    inlet_pressure = db.Column(db.Float)
    separator_pressure = db.Column(db.Float)
    temperature = db.Column(db.Float)
    liquid_rate = db.Column(db.Float)
    rate_diff = db.Column(db.Float)
    gross_rate = db.Column(db.Float)
    bsw = db.Column(db.Float)
    
    @property
    def net_production(self):
        if self.gross_rate is not None and self.bsw is not None:
            return self.gross_rate * (1 - self.bsw / 100)
        return None
    
    def to_dict(self):
        return {
            'id': self.id,
            'test_id': self.test_id,
            'time': self.time.isoformat() if self.time else None,
            'bean_size': self.bean_size,
            'inlet_pressure': self.inlet_pressure,
            'separator_pressure': self.separator_pressure,
            'temperature': self.temperature,
            'liquid_rate': self.liquid_rate,
            'rate_diff': self.rate_diff,
            'gross_rate': self.gross_rate,
            'bsw': self.bsw,
            'net_production': self.net_production
        }

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='operator')
    
    def set_password(self, password):
        self.password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    def check_password(self, password):
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()
    
    def generate_token(self, expires_in=3600):
        from flask import current_app
        payload = {
            'sub': str(self.id),
            'username': self.username,
            'role': self.role,
            'exp': dt.datetime.utcnow() + dt.timedelta(seconds=expires_in)
        }
        return jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    
    @staticmethod
    def verify_token(token):
        from flask import current_app
        try:
            payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            return User.query.get(payload['sub'])
        except:
            return None
    
    def to_dict(self, include_permissions=False):
        result = {
            'id': self.id,
            'username': self.username,
            'role': self.role
        }
        if include_permissions:
            result['permissions'] = {p.feature: p.allowed for p in self.permissions}
            result['allowed_features'] = [f[0] for f in FEATURES if f[0] not in result['permissions'] or result['permissions'][f[0]]]
        return result
    
    def can_access(self, feature):
        if self.role == 'admin':
            return True
        perm = UserPermission.query.filter_by(user_id=self.id, feature=feature).first()
        if not perm:
            return True
        return perm.allowed

FEATURES = [
    ('app_welltest', 'Access WellTest Pro'),
    ('app_crude_export', 'Access Crude Export'),
    ('dashboard', 'Dashboard'),
    ('new_test', 'New Test'),
    ('tests', 'View Tests'),
    ('wells', 'Wells'),
    ('analytics', 'Analytics'),
    ('import', 'Import Data'),
    ('export', 'Export Data'),
    ('settings', 'User Management'),
]

class UserPermission(db.Model):
    __tablename__ = 'user_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    feature = db.Column(db.String(50), nullable=False)
    allowed = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref=db.backref('permissions', lazy='dynamic', cascade='all, delete-orphan'))
    
    __table_args__ = (db.UniqueConstraint('user_id', 'feature'),)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'feature': self.feature,
            'allowed': self.allowed
        }
class CrudeExport(db.Model):
    __tablename__ = 'crude_exports'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    destination = db.Column(db.String(50), nullable=False) # TNP, INGENTIA, ACE, INTENTAL
    volume = db.Column(db.Float, nullable=False)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'destination': self.destination,
            'volume': self.volume,
            'remarks': self.remarks,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class DailyProduction(db.Model):
    __tablename__ = 'daily_production'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    oil_volume = db.Column(db.Float, nullable=False)
    gas_volume = db.Column(db.Float, default=0)
    water_volume = db.Column(db.Float, default=0)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'oil_volume': self.oil_volume,
            'gas_volume': self.gas_volume,
            'water_volume': self.water_volume,
            'remarks': self.remarks,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
