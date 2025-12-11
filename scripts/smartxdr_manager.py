#!/usr/bin/env python3
"""
SmartXDR Management Console
CLI tool for managing Users and API Keys
Usage: python scripts/smartxdr_manager.py
"""
import sys
import os
import secrets
import string
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from app.models.db_models import db, User, Role, APIKeyModel, APIKeyUsage
from flask_security.utils import hash_password
from app.utils.cryptography import hash_api_key


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str):
    """Print a styled header"""
    print("\n" + "═" * 60)
    print(f"  {title}")
    print("═" * 60)


def print_menu(title: str, options: list):
    """Print a styled menu"""
    print("\n╔" + "═" * 58 + "╗")
    print(f"║  {title:^54}  ║")
    print("╠" + "═" * 58 + "╣")
    for i, opt in enumerate(options):
        if opt == "---":
            print("╠" + "─" * 58 + "╣")
        else:
            print(f"║  {i}. {opt:<52}  ║")
    print("╚" + "═" * 58 + "╝")


def generate_password(length: int = 24) -> str:
    """Generate a strong random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*")
    ]
    password.extend(secrets.choice(alphabet) for _ in range(length - 4))
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def confirm(prompt: str) -> bool:
    """Ask for confirmation"""
    response = input(f"{prompt} [y/N]: ").strip().lower()
    return response == 'y'


# ═══════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def list_users():
    """List all users"""
    print_header("All Users")
    users = User.query.all()
    
    if not users:
        print("\n  No users found.")
        return
    
    print(f"\n  {'ID':<5} {'Username':<15} {'Email':<30} {'Role':<10} {'Active':<8}")
    print("  " + "-" * 70)
    
    for user in users:
        roles = ', '.join([r.name for r in user.roles]) or 'none'
        active = '✓' if user.active else '✗'
        print(f"  {user.id:<5} {user.username:<15} {user.email:<30} {roles:<10} {active:<8}")
    
    print()


def create_user():
    """Create a new user"""
    print_header("Create New User")
    
    # Get email
    email = input("\n  Email: ").strip()
    if not email or '@' not in email:
        print("  ✗ Invalid email")
        return
    
    if User.query.filter_by(email=email).first():
        print("  ✗ Email already exists")
        return
    
    # Get username
    username = input("  Username: ").strip()
    if not username:
        print("  ✗ Username required")
        return
    
    if User.query.filter_by(username=username).first():
        print("  ✗ Username already exists")
        return
    
    # Generate or enter password
    gen_password = generate_password()
    print(f"\n  💡 Generated password: {gen_password}")
    password = input("  Press Enter to use, or type custom: ").strip() or gen_password
    
    # Select role
    print("\n  Roles: 1=admin, 2=user")
    role_choice = input("  Select role [1]: ").strip() or '1'
    role_name = 'admin' if role_choice == '1' else 'user'
    
    role = Role.query.filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name, description=f'{role_name.title()} role')
        db.session.add(role)
        db.session.commit()
    
    # Create user
    from flask_security.datastore import SQLAlchemyUserDatastore
    user_datastore = SQLAlchemyUserDatastore(db, User, Role)
    
    new_user = user_datastore.create_user(
        email=email,
        username=username,
        password=hash_password(password),
        active=True
    )
    user_datastore.add_role_to_user(new_user, role)
    db.session.commit()
    
    print(f"\n  ✓ User created: {email}")
    print(f"  ✓ Password: {password}")
    print(f"  ✓ Role: {role_name}")


def delete_user():
    """Delete a user"""
    print_header("Delete User")
    list_users()
    
    email = input("\n  Enter email to delete: ").strip()
    user = User.query.filter_by(email=email).first()
    
    if not user:
        print("  ✗ User not found")
        return
    
    if confirm(f"  Delete user '{email}'?"):
        db.session.delete(user)
        db.session.commit()
        print(f"  ✓ User deleted: {email}")
    else:
        print("  ✗ Cancelled")


def reset_password():
    """Reset user password"""
    print_header("Reset Password")
    list_users()
    
    email = input("\n  Enter email: ").strip()
    user = User.query.filter_by(email=email).first()
    
    if not user:
        print("  ✗ User not found")
        return
    
    gen_password = generate_password()
    print(f"\n  💡 Generated password: {gen_password}")
    password = input("  Press Enter to use, or type custom: ").strip() or gen_password
    
    user.password = hash_password(password)
    db.session.commit()
    
    print(f"\n  ✓ Password reset for: {email}")
    print(f"  ✓ New password: {password}")


def user_management_menu():
    """User management submenu"""
    while True:
        print_menu("User Management", [
            "Back to Main Menu",
            "List Users",
            "Create User",
            "Delete User",
            "Reset Password"
        ])
        
        choice = input("\n  Select option: ").strip()
        
        if choice == '0':
            break
        elif choice == '1':
            list_users()
        elif choice == '2':
            create_user()
        elif choice == '3':
            delete_user()
        elif choice == '4':
            reset_password()
        
        input("\n  Press Enter to continue...")


# ═══════════════════════════════════════════════════════════════════════════════
# API KEY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def list_api_keys():
    """List all API keys"""
    print_header("All API Keys")
    keys = APIKeyModel.query.all()
    
    if not keys:
        print("\n  No API keys found.")
        return
    
    print(f"\n  {'ID':<5} {'Name':<20} {'Prefix':<10} {'Status':<10} {'Rate':<8} {'Uses':<8}")
    print("  " + "-" * 65)
    
    for key in keys:
        status = '✓ Active' if key.enabled and not key.is_expired else '✗ Disabled'
        if key.is_expired:
            status = '⏰ Expired'
        print(f"  {key.id:<5} {key.name:<20} {key.key_prefix:<10} {status:<10} {key.rate_limit:<8} {key.usage_count:<8}")
    
    print()


def create_api_key():
    """Create a new API key"""
    print_header("Create New API Key")
    
    # Get name
    name = input("\n  Key name: ").strip()
    if not name:
        print("  ✗ Name required")
        return
    
    if APIKeyModel.query.filter_by(name=name).first():
        print("  ✗ Name already exists")
        return
    
    # Get description
    description = input("  Description (optional): ").strip()
    
    # Get permissions
    print("\n  Permissions (comma-separated, or * for all):")
    print("  Examples: *, ai:ask, enrich:*, triage:read")
    perm_input = input("  Permissions [*]: ").strip() or '*'
    permissions = [p.strip() for p in perm_input.split(',')]
    
    # Get rate limit
    rate_input = input("  Rate limit per minute [60]: ").strip() or '60'
    try:
        rate_limit = int(rate_input)
    except ValueError:
        rate_limit = 60
    
    # Get expiration
    print("\n  Expiration:")
    print("  1. Never")
    print("  2. 30 days")
    print("  3. 90 days")
    print("  4. 1 year")
    exp_choice = input("  Select [1]: ").strip() or '1'
    
    expires_at = None
    if exp_choice == '2':
        expires_at = datetime.utcnow() + timedelta(days=30)
    elif exp_choice == '3':
        expires_at = datetime.utcnow() + timedelta(days=90)
    elif exp_choice == '4':
        expires_at = datetime.utcnow() + timedelta(days=365)
    
    # Generate key
    prefix = "sxdr"
    random_part = secrets.token_urlsafe(32)
    api_key = f"{prefix}_{random_part}"
    key_hash = hash_api_key(api_key)
    
    # Create model
    new_key = APIKeyModel(
        name=name,
        key_hash=key_hash,
        key_prefix=prefix,
        description=description,
        permissions=json.dumps(permissions),
        rate_limit=rate_limit,
        expires_at=expires_at,
        created_by='cli'
    )
    db.session.add(new_key)
    db.session.commit()
    
    print("\n" + "═" * 60)
    print("  ✓ API Key Created Successfully!")
    print("═" * 60)
    print(f"\n  Name: {name}")
    print(f"  Permissions: {permissions}")
    print(f"  Rate Limit: {rate_limit}/min")
    print(f"  Expires: {expires_at or 'Never'}")
    print("\n  ⚠️  SAVE THIS KEY (shown only once!):")
    print(f"\n  {api_key}")
    print("\n" + "═" * 60)


def delete_api_key():
    """Delete an API key"""
    print_header("Delete API Key")
    list_api_keys()
    
    name = input("\n  Enter key name to delete: ").strip()
    key = APIKeyModel.query.filter_by(name=name).first()
    
    if not key:
        print("  ✗ Key not found")
        return
    
    if confirm(f"  Delete key '{name}'?"):
        # Also delete usage logs
        APIKeyUsage.query.filter_by(key_hash=key.key_hash).delete()
        db.session.delete(key)
        db.session.commit()
        print(f"  ✓ Key deleted: {name}")
    else:
        print("  ✗ Cancelled")


def toggle_api_key():
    """Enable/Disable an API key"""
    print_header("Enable/Disable API Key")
    list_api_keys()
    
    name = input("\n  Enter key name: ").strip()
    key = APIKeyModel.query.filter_by(name=name).first()
    
    if not key:
        print("  ✗ Key not found")
        return
    
    key.enabled = not key.enabled
    db.session.commit()
    
    status = 'enabled' if key.enabled else 'disabled'
    print(f"\n  ✓ Key '{name}' is now {status}")


def view_key_usage():
    """View API key usage statistics"""
    print_header("API Key Usage")
    list_api_keys()
    
    name = input("\n  Enter key name (or Enter for all): ").strip()
    
    if name:
        key = APIKeyModel.query.filter_by(name=name).first()
        if not key:
            print("  ✗ Key not found")
            return
        
        logs = APIKeyUsage.query.filter_by(key_hash=key.key_hash).order_by(
            APIKeyUsage.created_at.desc()
        ).limit(20).all()
    else:
        logs = APIKeyUsage.query.order_by(
            APIKeyUsage.created_at.desc()
        ).limit(20).all()
    
    if not logs:
        print("\n  No usage logs found.")
        return
    
    print(f"\n  {'Time':<20} {'Endpoint':<30} {'Method':<8} {'Status':<8} {'IP':<15}")
    print("  " + "-" * 85)
    
    for log in logs:
        time_str = log.created_at.strftime('%Y-%m-%d %H:%M') if log.created_at else '-'
        print(f"  {time_str:<20} {log.endpoint[:28]:<30} {log.method:<8} {log.status_code:<8} {log.client_ip:<15}")


def api_key_management_menu():
    """API key management submenu"""
    while True:
        print_menu("API Key Management", [
            "Back to Main Menu",
            "List API Keys",
            "Create API Key",
            "Delete API Key",
            "Enable/Disable Key",
            "View Usage Logs"
        ])
        
        choice = input("\n  Select option: ").strip()
        
        if choice == '0':
            break
        elif choice == '1':
            list_api_keys()
        elif choice == '2':
            create_api_key()
        elif choice == '3':
            delete_api_key()
        elif choice == '4':
            toggle_api_key()
        elif choice == '5':
            view_key_usage()
        
        input("\n  Press Enter to continue...")


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def view_system_status():
    """View system status"""
    print_header("System Status")
    
    user_count = User.query.count()
    admin_count = User.query.join(User.roles).filter(Role.name == 'admin').count()
    key_count = APIKeyModel.query.count()
    active_keys = APIKeyModel.query.filter_by(enabled=True).count()
    total_usage = db.session.query(db.func.sum(APIKeyModel.usage_count)).scalar() or 0
    
    print(f"""
  ┌─────────────────────────────────────┐
  │  SmartXDR System Status             │
  ├─────────────────────────────────────┤
  │  Users:           {user_count:<5}             │
  │  Admins:          {admin_count:<5}             │
  │  API Keys:        {key_count:<5}             │
  │  Active Keys:     {active_keys:<5}             │
  │  Total API Calls: {total_usage:<10}        │
  └─────────────────────────────────────┘
    """)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════════

def main_menu(app):
    """Main menu loop"""
    with app.app_context():
        while True:
            clear_screen()
            print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║       ____                       _  __  ____  ____       ║
║      / ___| _ __ ___   __ _ _ __| |_\\ \\/ / _ \\|  _ \\      ║
║      \\___ \\| '_ ` _ \\ / _` | '__| __|\\  / | | | |_) |     ║
║       ___) | | | | | | (_| | |  | |_ /  \\ |_| |  _ <      ║
║      |____/|_| |_| |_|\\__,_|_|   \\__/_/\\_\\___/|_| \\_\\     ║
║                                                          ║
║              Management Console v1.0                     ║
║                                                          ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║    1. User Management                                    ║
║    2. API Key Management                                 ║
║    3. View System Status                                 ║
║                                                          ║
║    0. Exit                                               ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
            """)
            
            choice = input("  Select option: ").strip()
            
            if choice == '0':
                print("\n  Goodbye! 👋\n")
                break
            elif choice == '1':
                user_management_menu()
            elif choice == '2':
                api_key_management_menu()
            elif choice == '3':
                view_system_status()
                input("\n  Press Enter to continue...")


def main():
    """Main entry point"""
    try:
        print("\n  🚀 Initializing SmartXDR...")
        app = create_app()
        main_menu(app)
    except KeyboardInterrupt:
        print("\n\n  ✗ Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
