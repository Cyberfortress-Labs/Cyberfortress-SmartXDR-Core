#!/usr/bin/env python3
"""
Initialize admin database with Flask-Security
Creates tables and default admin user
"""
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from flask_security.core import Security
from flask_security.datastore import SQLAlchemyUserDatastore
from flask_security.utils import hash_password
from app.models.db_models import db, User, Role


def init_database():
    """Initialize database with tables and default admin user"""
    
    # Create Flask app with minimal config
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'init-secret-key'
    app.config['SECURITY_PASSWORD_SALT'] = 'init-salt'
    
    # Use absolute path for Windows compatibility
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'data' / 'smartxdr.db'
    db_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure data directory exists
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    security = Security(app, user_datastore)
    
    with app.app_context():
        # Create all tables
        print("Creating database tables...")
        db.create_all()
        
        # Create roles
        print("Creating roles...")
        admin_role = user_datastore.find_role('admin')
        if not admin_role:
            admin_role = user_datastore.create_role(
                name='admin',
                description='Administrator with full access'
            )
            print("✓ Created 'admin' role")
        else:
            print("✓ Role 'admin' already exists")
        
        user_role = user_datastore.find_role('user')
        if not user_role:
            user_role = user_datastore.create_role(
                name='user',
                description='Regular user with limited access'
            )
            print("✓ Created 'user' role")
        else:
            print("✓ Role 'user' already exists")
        
        # Create default admin user
        print("\nCreating default admin user...")
        admin_user = user_datastore.find_user(email='admin@cyberfortress.local')
        if not admin_user:
            admin_user = user_datastore.create_user(
                email='admin@cyberfortress.local',
                username='admin',
                password=hash_password('admin123'),
                active=True
            )
            user_datastore.add_role_to_user(admin_user, 'admin')
            print("✓ Created admin user:")
            print("  Email: admin@cyberfortress.local")
            print("  Username: admin")
            print("  Password: admin123")
            print("\n⚠️  IMPORTANT: Change the default password after first login!")
        else:
            print("✓ Admin user already exists")
        
        # Commit changes
        db.session.commit()
        
        print("\n✅ Database initialization complete!")
        print(f"Database file: {os.path.abspath('data/smartxdr.db')}")
        print("\nYou can now access the admin panel at: http://localhost:5000/admin")
        print("Login with: admin@cyberfortress.local / admin123")


if __name__ == '__main__':
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    
    try:
        init_database()
    except Exception as e:
        print(f"\n❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
