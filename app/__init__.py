"""
Flask application factory for Cyberfortress SmartXDR Core
"""
import os
import secrets
from pathlib import Path
from flask import Flask, request, redirect
from flask_cors import CORS
from flask_security.core import Security
from flask_security.datastore import SQLAlchemyUserDatastore
from flask_security.utils import hash_password
# Note: Old ChromaDB initialization removed - now using RAGService
# from app.core.database import initialize_database


# Global ChromaDB collection instance (legacy - kept for backward compatibility)
collection = None


def create_app():
    """
    Create and configure Flask application
    
    Returns:
        Flask app instance
    """
    app = Flask(__name__)
    
    # Enable CORS for all routes
    CORS(app)
    
    # Configuration
    app.config['JSON_SORT_KEYS'] = False
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True
    app.config['JSON_AS_ASCII'] = False  # Để tiếng Việt hiển thị đúng
    
    # Security configuration - Use persistent keys (from env vars or fixed default for dev)
    # IMPORTANT: Never regenerate these on restart - it breaks password verification!
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-12345678')
    app.config['SECURITY_PASSWORD_SALT'] = os.environ.get('SECURITY_PASSWORD_SALT', 'dev-salt-change-me-12345678')
    
    # Flask-Security password hashing (use argon2 - most secure)
    app.config['SECURITY_PASSWORD_HASH'] = 'argon2'
    app.config['SECURITY_PASSWORD_SCHEMES'] = ['argon2', 'bcrypt', 'pbkdf2_sha512']
    
    # Flask-Security settings
    app.config['SECURITY_REGISTERABLE'] = False  # Disable public registration
    app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
    app.config['SECURITY_USER_IDENTITY_ATTRIBUTES'] = [{'email': {'mapper': str.lower}}, {'username': {'mapper': str.lower}}]  # Allow login with email OR username
    app.config['SECURITY_POST_LOGIN_VIEW'] = '/admin/'
    app.config['SECURITY_POST_LOGOUT_VIEW'] = '/login'
    app.config['SECURITY_LOGIN_USER_TEMPLATE'] = 'security/login_user.html'
    
    # Flask-Security URL configuration
    app.config['SECURITY_URL_PREFIX'] = None
    app.config['SECURITY_BLUEPRINT_NAME'] = 'security'
    
    # Flask-Security flash messages
    app.config['SECURITY_FLASH_MESSAGES'] = True
    app.config['SECURITY_MSG_INVALID_PASSWORD'] = ('Invalid password', 'error')
    app.config['SECURITY_MSG_USER_DOES_NOT_EXIST'] = ('User does not exist', 'error')
    
    # Flask-Security redirect behavior - CRITICAL for proper redirects
    app.config['SECURITY_REDIRECT_BEHAVIOR'] = None  # Use traditional redirects, not SPA
    app.config['SECURITY_REDIRECT_HOST'] = None
    app.config['SECURITY_REDIRECT_ALLOW_SUBDOMAINS'] = False
    
    # CSRF Protection
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit for CSRF tokens
    
    # SQLAlchemy configuration - use db/app_data directory
    from app.config import APP_DATA_PATH
    db_path = Path(APP_DATA_PATH) / 'smartxdr.sqlite3'
    db_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    from app.models.db_models import db, User, Role
    db.init_app(app)
    
    # Setup Flask-Security
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security = Security(app, user_datastore)
    
    # Add signal handler for logging successful logins
    from flask_security import user_authenticated
    
    @user_authenticated.connect_via(app)
    def on_user_authenticated(sender, user, **extra):
        """Log when user is authenticated"""
        print(f"✓ User authenticated: {user.email}")

    
    # Create tables and roles (admin user should be created via scripts/create_superadmin.py)
    with app.app_context():
        db.create_all()
        
        # Create roles if they don't exist
        if not user_datastore.find_role('admin'):
            user_datastore.create_role(name='admin', description='Administrator')
        if not user_datastore.find_role('user'):
            user_datastore.create_role(name='user', description='Regular User')
        
        db.session.commit()
    
    # Note: Web admin removed - use scripts/smartxdr_manager.py for management
    
    # Register blueprints
    from app.routes.ai import ai_bp
    from app.routes.ioc import ioc_bp
    from app.routes.triage import triage_bp
    from app.routes.telegram import telegram_bp
    from app.routes.rag import rag_bp
    
    app.register_blueprint(ai_bp, url_prefix='/api/ai')
    app.register_blueprint(ioc_bp)
    app.register_blueprint(triage_bp, url_prefix='/api/triage')
    app.register_blueprint(telegram_bp, url_prefix='/api/telegram')
    app.register_blueprint(rag_bp)  # Already has /api/rag prefix in blueprint
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint"""
        return {'status': 'healthy', 'service': 'Cyberfortress SmartXDR Core'}, 200
    
    return app


def get_collection():
    """Get the global ChromaDB collection instance"""
    return collection
