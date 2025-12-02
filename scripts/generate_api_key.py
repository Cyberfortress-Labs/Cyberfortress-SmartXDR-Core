#!/usr/bin/env python3
"""
Generate API keys for SmartXDR

Usage:
    python scripts/generate_api_key.py --type master
    python scripts/generate_api_key.py --type iris
    python scripts/generate_api_key.py --type analyst --count 3
"""
import secrets
import argparse
import sys


def generate_key(prefix: str = "sxdr") -> str:
    """Generate a secure API key"""
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def main():
    parser = argparse.ArgumentParser(
        description='Generate SmartXDR API keys',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/generate_api_key.py --type master
  python scripts/generate_api_key.py --type iris  
  python scripts/generate_api_key.py --type analyst --count 3
  python scripts/generate_api_key.py --prefix custom --count 2
        """
    )
    parser.add_argument('--prefix', default='sxdr', help='Key prefix (default: sxdr)')
    parser.add_argument('--count', type=int, default=1, help='Number of keys to generate')
    parser.add_argument('--type', choices=['master', 'iris', 'analyst'], default='analyst',
                        help='Key type for .env format suggestion')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🔐 SmartXDR API Key Generator")
    print("=" * 70)
    
    for i in range(args.count):
        key = generate_key(args.prefix)
        print(f"\n🔑 Key {i+1}:")
        print(f"   {key}")
        print()
        
        if args.type == 'master':
            print(f"   📝 Add to .env:")
            print(f'   SMARTXDR_API_KEY="{key}"')
            print()
            print(f"   🔓 Permissions: FULL ACCESS (all endpoints)")
            
        elif args.type == 'iris':
            print(f"   📝 Add to .env:")
            print(f'   IRIS_API_KEY_FOR_SMARTXDR="{key}"')
            print()
            print(f"   🔓 Permissions: enrich:*, ai:*, network:*, triage:*, playbook:*")
            
        else:
            print(f"   📝 Add to .env (append to SMARTXDR_ADDITIONAL_API_KEYS):")
            print(f'   SMARTXDR_ADDITIONAL_API_KEYS="{key}:analyst_{i+1}:ai:ask,enrich:read"')
            print()
            print(f"   🔓 Permissions: ai:ask, enrich:read (customize as needed)")
    
    print("\n" + "=" * 70)
    print("📖 Usage examples:")
    print()
    print("  # Using X-API-Key header:")
    print("  curl -X POST http://localhost:8080/api/ai/ask \\")
    print("       -H 'X-API-Key: YOUR_KEY' \\")
    print("       -H 'Content-Type: application/json' \\")
    print("       -d '{\"query\": \"What is Suricata IP?\"}'")
    print()
    print("  # Using Authorization Bearer:")
    print("  curl -X POST http://localhost:8080/api/ai/ask \\")
    print("       -H 'Authorization: Bearer YOUR_KEY' \\")
    print("       -H 'Content-Type: application/json' \\")
    print("       -d '{\"query\": \"What is Suricata IP?\"}'")
    print()
    print("=" * 70)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
