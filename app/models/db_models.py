"""
SQLAlchemy models for SmartXDR
Uses Flask-Security-Too for user management
"""
from flask_sqlalchemy import SQLAlchemy
from flask_security import UserMixin, RoleMixin
from datetime import datetime

db = SQLAlchemy()

# Many-to-many relationship tables
roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id'))
)


class Role(db.Model, RoleMixin):
    """User roles (admin, user, etc.)"""
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    
    def __repr__(self):
        return f'<Role {self.name}>'


class User(db.Model, UserMixin):
    """Superuser/Admin accounts"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean(), default=True)
    fs_uniquifier = db.Column(db.String(255), unique=True, nullable=False)
    confirmed_at = db.Column(db.DateTime())
    
    # Relationships
    roles = db.relationship('Role', secondary=roles_users,
                          backref=db.backref('users', lazy='dynamic'))
    
    # Audit fields
    created_at = db.Column(db.DateTime(), default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(100))
    current_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<User {self.username}>'


class APIKeyModel(db.Model):
    """API Keys for external integrations"""
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    key_hash = db.Column(db.String(255), unique=True, nullable=False)
    key_prefix = db.Column(db.String(20), nullable=False)
    description = db.Column(db.Text)
    
    # Permissions stored as JSON
    permissions = db.Column(db.Text, nullable=False)  # JSON array
    
    # Rate limiting
    rate_limit = db.Column(db.Integer, default=60)
    
    # Status
    enabled = db.Column(db.Boolean(), default=True)
    
    # Expiration
    expires_at = db.Column(db.DateTime())
    
    # Audit
    created_at = db.Column(db.DateTime(), default=datetime.utcnow)
    created_by = db.Column(db.String(255))
    last_used_at = db.Column(db.DateTime())
    usage_count = db.Column(db.Integer, default=0)
    
    # Metadata
    metadata_json = db.Column(db.Text)  # JSON object
    
    def __repr__(self):
        return f'<APIKey {self.name}>'
    
    @property
    def is_expired(self):
        """Check if key is expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @property
    def is_active(self):
        """Check if key is active and not expired"""
        return self.enabled and not self.is_expired


class APIKeyUsage(db.Model):
    """API Key usage logs"""
    __tablename__ = 'api_key_usage'
    
    id = db.Column(db.Integer, primary_key=True)
    key_hash = db.Column(db.String(255), db.ForeignKey('api_keys.key_hash'), nullable=False)
    endpoint = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10))
    client_ip = db.Column(db.String(100))
    user_agent = db.Column(db.String(255))
    status_code = db.Column(db.Integer)
    response_time_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime(), default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Usage {self.endpoint} at {self.created_at}>'
