#!/usr/bin/env python3
"""
SmartXDR API Key Manager CLI
Manage API keys stored in database

Usage:
    python scripts/manage_api_keys.py create --name "IRIS" --permissions "enrich:*,ai:*"
    python scripts/manage_api_keys.py list
    python scripts/manage_api_keys.py stats master
    python scripts/manage_api_keys.py revoke analyst_1
    python scripts/manage_api_keys.py delete old_key
"""
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.api_key import APIKey


def create_key(args):
    """Create a new API key"""
    api_key = APIKey(args.db)
    
    # Parse permissions
    permissions = [p.strip() for p in args.permissions.split(',')]
    
    # Create key
    result = api_key.create(
        name=args.name,
        permissions=permissions,
        description=args.description or "",
        rate_limit=args.rate_limit,
        expires_in_days=args.expires,
        created_by=args.created_by,
        prefix=args.prefix
    )
    
    if result:
        print("\n" + "=" * 70)
        print("🔑 API Key Created Successfully!")
        print("=" * 70)
        print(f"\n🔐 API Key (SAVE THIS - shown only once!):")
        print(f"   {result['key']}")
        print(f"\n📝 Details:")
        print(f"   Name: {result['name']}")
        print(f"   Permissions: {', '.join(result['permissions'])}")
        print(f"   Rate Limit: {result['rate_limit']} req/min")
        if result['expires_at']:
            print(f"   Expires: {result['expires_at']}")
        print(f"\n✅ Add to your .env or use directly:")
        print(f'   SMARTXDR_API_KEY="{result["key"]}"')
        print(f"\n📖 Test with curl:")
        print(f'   curl -X POST http://localhost:8080/api/ai/ask \\')
        print(f'        -H "X-API-Key: {result["key"]}" \\')
        print(f'        -H "Content-Type: application/json" \\')
        print(f'        -d \'{{"query": "What is Suricata?"}}\'')
        print("\n" + "=" * 70 + "\n")
    else:
        print(f"❌ Failed to create API key: {args.name} (may already exist)")
        sys.exit(1)


def list_keys(args):
    """List all API keys"""
    api_key = APIKey(args.db)
    keys = api_key.list_keys(include_disabled=args.all)
    
    print("\n" + "=" * 100)
    print("🔑 SmartXDR API Keys")
    print("=" * 100)
    
    if not keys:
        print("\nNo API keys found.")
        print("\nCreate one with:")
        print("  python scripts/manage_api_keys.py create --name \"My Key\" --permissions \"ai:*\"")
    else:
        print(f"\nTotal: {len(keys)} key(s)\n")
        
        for key in keys:
            status = "🟢 ACTIVE" if key['enabled'] else "🔴 REVOKED"
            expired = ""
            if key['expires_at']:
                exp_date = datetime.fromisoformat(key['expires_at'])
                if datetime.now() > exp_date:
                    status = "⏰ EXPIRED"
                    expired = f" (expired {key['expires_at']})"
                else:
                    expired = f" (expires {key['expires_at']})"
            
            print(f"  {status} {key['name']}")
            print(f"     Prefix: {key['key_prefix']}")
            print(f"     Permissions: {', '.join(key['permissions'])}")
            print(f"     Rate Limit: {key['rate_limit']} req/min")
            print(f"     Created: {key['created_at']} by {key['created_by']}{expired}")
            if key['last_used_at']:
                print(f"     Last Used: {key['last_used_at']} ({key['usage_count']} total requests)")
            else:
                print(f"     Last Used: Never")
            if key['description']:
                print(f"     Description: {key['description']}")
            print()
    
    print("=" * 100 + "\n")


def show_stats(args):
    """Show usage statistics for a key"""
    api_key = APIKey(args.db)
    stats = api_key.get_usage_stats(args.name, args.days)
    
    if not stats:
        print(f"❌ API key not found: {args.name}")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print(f"📊 Usage Statistics: {stats['name']}")
    print("=" * 70)
    print(f"\nPeriod: Last {stats['period_days']} days")
    print(f"Total Requests: {stats['total_requests']}")
    print(f"Avg Response Time: {stats['avg_response_time_ms']} ms")
    print(f"Max Response Time: {stats['max_response_time_ms']} ms")
    
    print(f"\n📈 Top Endpoints:")
    for ep in stats['top_endpoints']:
        print(f"   {ep['endpoint']}: {ep['count']} requests")
    
    print(f"\n📉 Status Codes:")
    for code, count in stats['status_codes'].items():
        emoji = "✅" if code == 200 else "⚠️" if code < 500 else "❌"
        print(f"   {emoji} {code}: {count} requests")
    
    print("\n" + "=" * 70 + "\n")


def revoke_key(args):
    """Revoke (disable) an API key"""
    api_key = APIKey(args.db)
    
    if api_key.revoke(args.name):
        print(f"✅ API key revoked: {args.name}")
        print("   The key is now disabled and cannot be used.")
        print("   Use 'update --enabled true' to re-enable it.")
    else:
        print(f"❌ Failed to revoke key: {args.name} (not found)")
        sys.exit(1)


def delete_key(args):
    """Permanently delete an API key"""
    if not args.confirm:
        print(f"⚠️  Are you sure you want to DELETE '{args.name}'?")
        print("   This action cannot be undone!")
        confirm = input("   Type the key name to confirm: ")
        if confirm != args.name:
            print("❌ Deletion cancelled.")
            sys.exit(0)
    
    api_key = APIKey(args.db)
    
    if api_key.delete(args.name):
        print(f"✅ API key deleted: {args.name}")
        print("   All usage logs for this key have been removed.")
    else:
        print(f"❌ Failed to delete key: {args.name} (not found)")
        sys.exit(1)


def update_key(args):
    """Update API key properties"""
    api_key = APIKey(args.db)
    
    permissions = None
    if args.permissions:
        permissions = [p.strip() for p in args.permissions.split(',')]
    
    enabled = None
    if args.enabled is not None:
        enabled = args.enabled.lower() == 'true'
    
    if api_key.update(
        name=args.name,
        permissions=permissions,
        rate_limit=args.rate_limit,
        description=args.description,
        enabled=enabled
    ):
        print(f"✅ API key updated: {args.name}")
    else:
        print(f"❌ Failed to update key: {args.name} (not found or no changes)")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Manage SmartXDR API Keys',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new key for IRIS integration
  python scripts/manage_api_keys.py create --name "IRIS" \\
      --permissions "enrich:*,ai:*,triage:*" \\
      --rate-limit 1000 \\
      --description "IRIS SOAR integration"
  
  # Create analyst key with limited permissions
  python scripts/manage_api_keys.py create --name "analyst_john" \\
      --permissions "ai:ask,enrich:read" \\
      --expires 90
  
  # List all keys
  python scripts/manage_api_keys.py list
  
  # Show usage statistics
  python scripts/manage_api_keys.py stats master --days 7
  
  # Update key permissions
  python scripts/manage_api_keys.py update analyst_john \\
      --permissions "ai:*,enrich:read"
  
  # Revoke a key
  python scripts/manage_api_keys.py revoke old_key
  
  # Delete a key permanently
  python scripts/manage_api_keys.py delete old_key --confirm
        """
    )
    
    parser.add_argument('--db', default='data/api_keys.db',
                        help='Database path (default: data/api_keys.db)')
    
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new API key')
    create_parser.add_argument('--name', required=True, help='Key name/identifier')
    create_parser.add_argument('--permissions', required=True,
                                help='Comma-separated permissions (e.g., "ai:*,enrich:read")')
    create_parser.add_argument('--description', help='Key description')
    create_parser.add_argument('--rate-limit', type=int, default=60,
                                help='Rate limit (req/min, default: 60)')
    create_parser.add_argument('--expires', type=int, help='Expiration in days')
    create_parser.add_argument('--created-by', default='admin', help='Creator name')
    create_parser.add_argument('--prefix', default='sxdr', help='Key prefix (default: sxdr)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all API keys')
    list_parser.add_argument('--all', action='store_true',
                             help='Include disabled/revoked keys')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show usage statistics')
    stats_parser.add_argument('name', help='Key name')
    stats_parser.add_argument('--days', type=int, default=7,
                              help='Number of days (default: 7)')
    
    # Revoke command
    revoke_parser = subparsers.add_parser('revoke', help='Revoke (disable) an API key')
    revoke_parser.add_argument('name', help='Key name to revoke')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Permanently delete an API key')
    delete_parser.add_argument('name', help='Key name to delete')
    delete_parser.add_argument('--confirm', action='store_true',
                                help='Skip confirmation prompt')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update API key properties')
    update_parser.add_argument('name', help='Key name')
    update_parser.add_argument('--permissions', help='New permissions (comma-separated)')
    update_parser.add_argument('--rate-limit', type=int, help='New rate limit')
    update_parser.add_argument('--description', help='New description')
    update_parser.add_argument('--enabled', help='Enable/disable (true/false)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Route to handler
    if args.command == 'create':
        create_key(args)
    elif args.command == 'list':
        list_keys(args)
    elif args.command == 'stats':
        show_stats(args)
    elif args.command == 'revoke':
        revoke_key(args)
    elif args.command == 'delete':
        delete_key(args)
    elif args.command == 'update':
        update_key(args)


if __name__ == '__main__':
    main()
