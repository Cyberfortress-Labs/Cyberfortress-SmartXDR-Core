"""
Flask-Admin with Flask-Security-Too integration
Auto-generates CRUD interface from SQLAlchemy models
"""
import secrets
import json
from flask import redirect, url_for, request, flash
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.actions import action
from flask_login import current_user
from datetime import datetime, timedelta

from app.models.db_models import db, User, Role, APIKeyModel, APIKeyUsage
from app.utils.cryptography import hash_api_key


class SecureModelView(ModelView):
    """Base ModelView with authentication"""
    
    def is_accessible(self):
        """Only allow access to authenticated users with admin role"""
        return (current_user.is_active and
                current_user.is_authenticated and
                current_user.has_role('admin'))
    
    def inaccessible_callback(self, name, **kwargs):
        """Redirect to login if not authenticated"""
        return redirect(url_for('security.login', next=request.url))


class SecureAdminIndexView(AdminIndexView):
    """Secure admin index view"""
    
    def is_accessible(self):
        return (current_user.is_active and
                current_user.is_authenticated and
                current_user.has_role('admin'))
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('security.login', next=request.url))


class UserAdmin(SecureModelView):
    """Admin view for User model"""
    
    # Columns to display in list view
    column_list = ['username', 'email', 'active', 'roles', 'created_at', 'last_login_at', 'login_count']
    
    # Columns searchable
    column_searchable_list = ['username', 'email']
    
    # Columns filterable
    column_filters = ['active', 'roles', 'created_at']
    
    # Column labels
    column_labels = {
        'fs_uniquifier': 'Unique ID',
        'confirmed_at': 'Confirmed',
        'last_login_at': 'Last Login',
        'current_login_at': 'Current Login',
        'last_login_ip': 'Last IP',
        'current_login_ip': 'Current IP',
    }
    
    # Columns excluded from forms
    form_excluded_columns = ['password', 'fs_uniquifier', 'last_login_at', 
                            'current_login_at', 'last_login_ip', 
                            'current_login_ip', 'login_count']
    
    # Enable creation
    can_create = True
    can_edit = True
    can_delete = True
    
    # Details view
    column_details_list = ['id', 'username', 'email', 'active', 'roles', 
                          'created_at', 'last_login_at', 'login_count']


class RoleAdmin(SecureModelView):
    """Admin view for Role model"""
    
    column_list = ['name', 'description']
    column_searchable_list = ['name', 'description']
    
    form_columns = ['name', 'description']
    
    can_create = True
    can_edit = True
    can_delete = True


class APIKeyAdmin(SecureModelView):
    """Admin view for API Key model"""
    
    # List view columns
    column_list = ['name', 'key_prefix', 'enabled', 'rate_limit', 
                   'created_by', 'created_at', 'last_used_at', 'usage_count']
    
    # Searchable
    column_searchable_list = ['name', 'key_prefix', 'description']
    
    # Filterable
    column_filters = ['enabled', 'created_by', 'created_at', 'expires_at']
    
    # Labels
    column_labels = {
        'key_hash': 'Key Hash',
        'key_prefix': 'Prefix',
        'rate_limit': 'Rate Limit (req/min)',
        'created_by': 'Created By',
        'created_at': 'Created',
        'last_used_at': 'Last Used',
        'usage_count': 'Usage Count',
        'metadata_json': 'Metadata (JSON)',
    }
    
    # Form configuration
    form_excluded_columns = ['key_hash', 'last_used_at', 'usage_count', 'key_prefix']
    
    # Column formatters
    column_formatters = {
        'permissions': lambda v, c, m, p: ', '.join(json.loads(m.permissions) if m.permissions else []),
        'enabled': lambda v, c, m, p: '✓ Active' if m.enabled else '✗ Disabled',
    }
    
    # Details view
    column_details_list = ['id', 'name', 'key_prefix', 'description', 
                          'permissions', 'rate_limit', 'enabled', 
                          'expires_at', 'created_at', 'created_by',
                          'last_used_at', 'usage_count']
    
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    
    # Custom create form
    def create_model(self, form):
        """Override create to generate API key"""
        try:
            # Generate API key
            prefix = "sxdr"
            random_part = secrets.token_urlsafe(32)
            api_key = f"{prefix}_{random_part}"
            
            # Hash the key
            key_hash = hash_api_key(api_key)
            
            # Create model
            model = self.model()
            form.populate_obj(model)
            model.key_hash = key_hash
            model.key_prefix = prefix
            model.created_at = datetime.utcnow()
            model.created_by = current_user.username
            
            # Handle permissions (convert list to JSON if needed)
            if isinstance(model.permissions, list):
                model.permissions = json.dumps(model.permissions)
            
            db.session.add(model)
            db.session.commit()
            
            # Flash the API key (only shown once!)
            flash(f'API Key created successfully! SAVE THIS KEY (shown only once): {api_key}', 'success')
            flash(f'Key Hash: {key_hash[:20]}...', 'info')
            
            return model
        except Exception as ex:
            if not self.handle_view_exception(ex):
                flash(f'Failed to create record. {str(ex)}', 'error')
            db.session.rollback()
            return False
    
    @action('enable', 'Enable', 'Are you sure you want to enable selected keys?')
    def action_enable(self, ids):
        """Bulk enable API keys"""
        try:
            query = APIKeyModel.query.filter(APIKeyModel.id.in_(ids))
            count = query.update({APIKeyModel.enabled: True}, synchronize_session=False)
            db.session.commit()
            flash(f'{count} API key(s) enabled successfully.', 'success')
        except Exception as ex:
            flash(f'Failed to enable keys. {str(ex)}', 'error')
    
    @action('disable', 'Disable', 'Are you sure you want to disable selected keys?')
    def action_disable(self, ids):
        """Bulk disable API keys"""
        try:
            query = APIKeyModel.query.filter(APIKeyModel.id.in_(ids))
            count = query.update({APIKeyModel.enabled: False}, synchronize_session=False)
            db.session.commit()
            flash(f'{count} API key(s) disabled successfully.', 'success')
        except Exception as ex:
            flash(f'Failed to disable keys. {str(ex)}', 'error')
    can_delete = True
    can_view_details = True


class APIKeyUsageAdmin(SecureModelView):
    """Admin view for API Key usage logs"""
    
    # List view
    column_list = ['created_at', 'key_hash', 'endpoint', 'method', 
                   'status_code', 'response_time_ms', 'client_ip']
    
    # Searchable
    column_searchable_list = ['endpoint', 'key_hash', 'client_ip']
    
    # Filterable
    column_filters = ['method', 'status_code', 'created_at']
    
    # Labels
    column_labels = {
        'key_hash': 'API Key',
        'response_time_ms': 'Response Time (ms)',
        'client_ip': 'Client IP',
        'user_agent': 'User Agent',
    }
    
    # Default sort
    column_default_sort = ('created_at', True)  # Descending
    
    # Read-only
    can_create = False
    can_edit = False
    can_delete = True  # Allow cleanup of old logs
    can_view_details = True


def init_admin(app):
    """Initialize Flask-Admin with SQLAlchemy models
    
    Args:
        app: Flask application instance
    """
    # Create admin interface
    admin = Admin(
        app,
        name='SmartXDR Admin',
        index_view=SecureAdminIndexView(name='Dashboard', url='/admin')
    )
    
    # Add model views
    admin.add_view(UserAdmin(User, db.session, name='Users', category='Security'))
    admin.add_view(RoleAdmin(Role, db.session, name='Roles', category='Security'))
    admin.add_view(APIKeyAdmin(APIKeyModel, db.session, name='API Keys', category='API Management'))
    admin.add_view(APIKeyUsageAdmin(APIKeyUsage, db.session, name='Usage Logs', category='API Management'))
    
    return admin

