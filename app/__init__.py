"""
Flask application factory for Cyberfortress SmartXDR Core
"""
import os
import secrets
from pathlib import Path
from flask import Flask
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
    
    # Security configuration
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    app.config['SECURITY_PASSWORD_SALT'] = secrets.token_hex(16)
    
    # Flask-Security settings
    app.config['SECURITY_REGISTERABLE'] = False  # Disable public registration
    app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
    app.config['SECURITY_POST_LOGIN_VIEW'] = '/admin'
    app.config['SECURITY_POST_LOGOUT_VIEW'] = '/admin'
    
    # SQLAlchemy configuration - use absolute path for Windows compatibility
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'data' / 'admin.db'
    db_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure data directory exists
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize database
    from app.models.db_models import db, User, Role
    db.init_app(app)
    
    # Setup Flask-Security
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security = Security(app, user_datastore)
    
    # Create tables and default admin user
    with app.app_context():
        db.create_all()
        
        # Create roles if they don't exist
        if not user_datastore.find_role('admin'):
            user_datastore.create_role(name='admin', description='Administrator')
        if not user_datastore.find_role('user'):
            user_datastore.create_role(name='user', description='Regular User')
        
        # Create default admin user if no users exist
        if not user_datastore.find_user(email='admin@cyberfortress.local'):
            admin_user = user_datastore.create_user(
                email='admin@cyberfortress.local',
                username='admin',
                password=hash_password('admin123'),
                active=True
            )
            user_datastore.add_role_to_user(admin_user, 'admin')
        
        db.session.commit()
    
    # Note: ChromaDB initialization moved to RAGService
    # Old global collection no longer needed as routes now use RAGService directly
    
    # Initialize Flask-Admin (after Flask-Security)
    from app.admin import init_admin
    init_admin(app)
    
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
