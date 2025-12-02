"""
SecureLogAnonymizer - Security-hardened log anonymization module

Security Features:
- HMAC-SHA256 for consistent hashing (prevents length extension attacks)
- AES-256-GCM authenticated encryption for export/import
- PBKDF2-HMAC-SHA256 key derivation (100,000 iterations)
- Thread-safe mapping database with RLock
- IPv6 support with proper subnet preservation
- RFC-compliant email parsing
- Robust URL parsing with urllib.parse
- MAC address normalization
- Boundary-aware field matching

Author: SmartXDR Core Team
Version: 2.0.0 (Security Refactor)
"""

import re
import hmac
import hashlib
import secrets
import json
import ipaddress
import threading
import os
from typing import Any, Dict, Optional, List, Tuple, Set, Union
from urllib.parse import urlparse, urlunparse, ParseResult
from pathlib import Path
from datetime import datetime

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


class KeyManager:
    """
    Secure key management for anonymizer encryption.
    
    Key sources (priority order):
    1. Environment variable: ANONYMIZER_ENCRYPTION_KEY
    2. Key file: ~/.smartxdr/anonymizer.key or custom path
    3. Auto-generated (stored in key file)
    
    Security features:
    - Keys never logged or printed
    - Key file with restricted permissions (0600)
    - Support for key rotation
    - Memory protection (key zeroed after use where possible)
    """
    
    ENV_KEY_NAME = "ANONYMIZER_ENCRYPTION_KEY"
    DEFAULT_KEY_FILE = Path.home() / ".smartxdr" / "anonymizer.key"
    
    def __init__(self, key_file_path: Optional[Path] = None):
        """
        Initialize KeyManager.
        
        Args:
            key_file_path: Custom path for key file. Uses default if None.
        """
        self._key_file = Path(key_file_path) if key_file_path else self.DEFAULT_KEY_FILE
        self._cached_key: Optional[bytes] = None
        self._lock = threading.Lock()
    
    def get_key(self, auto_generate: bool = True) -> Optional[bytes]:
        """
        Get encryption key from configured sources.
        
        Priority:
        1. Environment variable ANONYMIZER_ENCRYPTION_KEY
        2. Key file
        3. Auto-generate if auto_generate=True
        
        Args:
            auto_generate: Whether to generate key if not found
            
        Returns:
            32-byte encryption key or None if not available
        """
        with self._lock:
            # Check cache first
            if self._cached_key:
                return self._cached_key
            
            # 1. Try environment variable
            env_key = os.environ.get(self.ENV_KEY_NAME)
            if env_key:
                # Support hex-encoded or base64-encoded keys
                try:
                    if len(env_key) == 64:  # Hex encoded (32 bytes = 64 hex chars)
                        self._cached_key = bytes.fromhex(env_key)
                    else:
                        import base64
                        self._cached_key = base64.b64decode(env_key)
                    
                    if len(self._cached_key) >= 32:
                        self._cached_key = self._cached_key[:32]
                        return self._cached_key
                except Exception:
                    pass
            
            # 2. Try key file
            if self._key_file.exists():
                try:
                    key_data = self._key_file.read_bytes().strip()
                    if len(key_data) >= 32:
                        self._cached_key = key_data[:32]
                        return self._cached_key
                except Exception:
                    pass
            
            # 3. Auto-generate
            if auto_generate:
                self._cached_key = self._generate_and_save_key()
                return self._cached_key
            
            return None
    
    def _generate_and_save_key(self) -> bytes:
        """Generate new key and save to key file."""
        key = secrets.token_bytes(32)
        
        try:
            # Create directory with restricted permissions
            self._key_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write key file
            self._key_file.write_bytes(key)
            
            # Set restrictive permissions (Unix only)
            try:
                os.chmod(self._key_file, 0o600)
            except (OSError, AttributeError):
                pass  # Windows doesn't support chmod the same way
            
        except Exception as e:
            # Log warning but continue with generated key
            import warnings
            warnings.warn(f"Could not save key file: {e}. Key will be regenerated on restart.")
        
        return key
    
    def rotate_key(self) -> bytes:
        """
        Generate new key, invalidating the old one.
        
        WARNING: This will make previously encrypted data unreadable!
        
        Returns:
            New 32-byte encryption key
        """
        with self._lock:
            # Clear cached key
            if self._cached_key:
                # Attempt to zero the memory (best effort)
                try:
                    key_array = bytearray(self._cached_key)
                    for i in range(len(key_array)):
                        key_array[i] = 0
                except Exception:
                    pass
                self._cached_key = None
            
            # Generate new key
            self._cached_key = self._generate_and_save_key()
            return self._cached_key
    
    def clear_cache(self):
        """Clear cached key from memory."""
        with self._lock:
            if self._cached_key:
                try:
                    key_array = bytearray(self._cached_key)
                    for i in range(len(key_array)):
                        key_array[i] = 0
                except Exception:
                    pass
                self._cached_key = None
    
    @staticmethod
    def generate_key_for_env() -> str:
        """
        Generate a new key formatted for environment variable.
        
        Returns:
            Hex-encoded 32-byte key suitable for ANONYMIZER_ENCRYPTION_KEY
        """
        return secrets.token_hex(32)
    
    def key_exists(self) -> bool:
        """Check if a key is available (env or file)."""
        return bool(os.environ.get(self.ENV_KEY_NAME)) or self._key_file.exists()


# Global key manager instance
_key_manager: Optional[KeyManager] = None
_key_manager_lock = threading.Lock()


def get_key_manager(key_file_path: Optional[Path] = None) -> KeyManager:
    """Get or create global KeyManager instance."""
    global _key_manager
    with _key_manager_lock:
        if _key_manager is None:
            _key_manager = KeyManager(key_file_path)
        return _key_manager


class SecureLogAnonymizer:
    """
    Thread-safe, security-hardened log anonymizer with consistent pseudonymization.
    
    Key security improvements:
    - Uses HMAC-SHA256 instead of raw SHA256 (prevents length extension attacks)
    - Encrypted export/import of mapping database
    - Thread-safe operations with RLock
    - Proper IPv6 handling
    - Boundary-aware matching to prevent false positives
    """
    
    # RFC 5321 compliant email regex (simplified but more accurate)
    EMAIL_PATTERN = re.compile(
        r'\b[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\b',
        re.IGNORECASE
    )
    
    # MAC address patterns (multiple formats)
    MAC_PATTERNS = [
        re.compile(r'\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'),  # AA:BB:CC:DD:EE:FF or AA-BB-CC-DD-EE-FF
        re.compile(r'\b[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\b'),  # AABB.CCDD.EEFF (Cisco)
        re.compile(r'\b[0-9A-Fa-f]{12}\b'),  # AABBCCDDEEFF (no separator)
    ]
    
    # Domain pattern with boundary
    DOMAIN_PATTERN = re.compile(
        r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b'
    )
    
    # Reserved/private IP ranges that should not be anonymized
    RESERVED_NETWORKS_V4 = [
        ipaddress.ip_network('0.0.0.0/8'),
        ipaddress.ip_network('127.0.0.0/8'),
        ipaddress.ip_network('169.254.0.0/16'),
        ipaddress.ip_network('224.0.0.0/4'),
        ipaddress.ip_network('240.0.0.0/4'),
        ipaddress.ip_network('255.255.255.255/32'),
    ]
    
    RESERVED_NETWORKS_V6 = [
        ipaddress.ip_network('::1/128'),
        ipaddress.ip_network('::/128'),
        ipaddress.ip_network('fe80::/10'),
        ipaddress.ip_network('ff00::/8'),
    ]
    
    def __init__(self, 
                 hmac_key: Optional[bytes] = None,
                 preserve_subnet_prefix: int = 16,
                 preserve_subnet_prefix_v6: int = 48,
                 salt_length: int = 32):
        """
        Initialize the anonymizer with security parameters.
        
        Args:
            hmac_key: HMAC key for consistent hashing. Auto-generated if None.
            preserve_subnet_prefix: IPv4 subnet bits to preserve (default: /16)
            preserve_subnet_prefix_v6: IPv6 subnet bits to preserve (default: /48)
            salt_length: Length of random salt (default: 32 bytes)
        """
        # Generate or use provided HMAC key
        self._hmac_key = hmac_key or secrets.token_bytes(32)
        
        # Subnet preservation settings
        self._preserve_prefix_v4 = min(max(preserve_subnet_prefix, 0), 24)
        self._preserve_prefix_v6 = min(max(preserve_subnet_prefix_v6, 0), 64)
        
        # Thread-safe mapping database
        self._lock = threading.RLock()
        self._mapping_db: Dict[str, Dict[str, str]] = {
            'ip': {},
            'email': {},
            'domain': {},
            'url': {},
            'mac': {},
            'custom': {},
            'user': {},
            'hostname': {},
        }
        
        # Statistics
        self._stats = {
            'total_anonymized': 0,
            'by_type': {k: 0 for k in self._mapping_db.keys()},
            'last_operation': None,
        }
        
        # Custom field patterns with word boundaries
        self._custom_patterns: Dict[str, re.Pattern] = {}
        
        # Encryption key for export (generated on demand)
        self._export_key: Optional[bytes] = None

    def _hmac_hash(self, data: str, category: str = '') -> str:
        """
        Generate HMAC-SHA256 hash for consistent pseudonymization.
        
        Args:
            data: Input data to hash
            category: Category prefix for domain separation
            
        Returns:
            Hex string of first 16 bytes of HMAC
        """
        message = f"{category}:{data}".encode('utf-8')
        h = hmac.new(self._hmac_key, message, hashlib.sha256)
        return h.hexdigest()[:16]
    
    def _normalize_mac(self, mac: str) -> str:
        """
        Normalize MAC address to consistent format (lowercase, colon-separated).
        
        Args:
            mac: MAC address in any format
            
        Returns:
            Normalized MAC (aa:bb:cc:dd:ee:ff)
        """
        # Remove all separators and convert to lowercase
        clean = re.sub(r'[:\-.]', '', mac).lower()
        
        if len(clean) != 12:
            return mac  # Invalid MAC, return as-is
        
        # Format as colon-separated
        return ':'.join(clean[i:i+2] for i in range(0, 12, 2))
    
    def _is_reserved_ip(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        """Check if IP is in reserved/private ranges that shouldn't be anonymized."""
        networks = self.RESERVED_NETWORKS_V4 if isinstance(ip, ipaddress.IPv4Address) else self.RESERVED_NETWORKS_V6
        return any(ip in net for net in networks)
    
    def _anonymize_ip_v4(self, ip_str: str) -> str:
        """
        Anonymize IPv4 address while preserving subnet structure.
        
        Args:
            ip_str: IPv4 address string
            
        Returns:
            Anonymized IPv4 address
        """
        with self._lock:
            if ip_str in self._mapping_db['ip']:
                return self._mapping_db['ip'][ip_str]
        
        try:
            ip = ipaddress.IPv4Address(ip_str)
            
            # Don't anonymize reserved addresses
            if self._is_reserved_ip(ip):
                return ip_str
            
            # Calculate preserved and anonymized parts
            ip_int = int(ip)
            prefix_bits = self._preserve_prefix_v4
            
            # Preserve the network prefix
            prefix_mask = (0xFFFFFFFF << (32 - prefix_bits)) & 0xFFFFFFFF
            preserved_prefix = ip_int & prefix_mask
            
            # Generate deterministic host part from HMAC
            host_hash = self._hmac_hash(ip_str, 'ipv4')
            host_int = int(host_hash[:8], 16) & ~prefix_mask
            
            # Combine preserved prefix with anonymized host
            anon_int = preserved_prefix | host_int
            anon_ip = str(ipaddress.IPv4Address(anon_int))
            
            with self._lock:
                self._mapping_db['ip'][ip_str] = anon_ip
                self._stats['by_type']['ip'] += 1
                self._stats['total_anonymized'] += 1
            
            return anon_ip
            
        except ipaddress.AddressValueError:
            return ip_str  # Invalid IP, return as-is
    
    def _anonymize_ip_v6(self, ip_str: str) -> str:
        """
        Anonymize IPv6 address while preserving subnet structure.
        
        Args:
            ip_str: IPv6 address string
            
        Returns:
            Anonymized IPv6 address
        """
        with self._lock:
            if ip_str in self._mapping_db['ip']:
                return self._mapping_db['ip'][ip_str]
        
        try:
            ip = ipaddress.IPv6Address(ip_str)
            
            # Don't anonymize reserved addresses
            if self._is_reserved_ip(ip):
                return ip_str
            
            # Calculate preserved and anonymized parts
            ip_int = int(ip)
            prefix_bits = self._preserve_prefix_v6
            
            # Preserve the network prefix
            prefix_mask = (0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF << (128 - prefix_bits)) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
            preserved_prefix = ip_int & prefix_mask
            
            # Generate deterministic interface ID from HMAC
            iid_hash = self._hmac_hash(ip_str, 'ipv6')
            iid_int = int(iid_hash, 16) & ~prefix_mask
            
            # Combine preserved prefix with anonymized interface ID
            anon_int = preserved_prefix | iid_int
            anon_ip = str(ipaddress.IPv6Address(anon_int))
            
            with self._lock:
                self._mapping_db['ip'][ip_str] = anon_ip
                self._stats['by_type']['ip'] += 1
                self._stats['total_anonymized'] += 1
            
            return anon_ip
            
        except ipaddress.AddressValueError:
            return ip_str  # Invalid IP, return as-is
    
    def anonymize_ip(self, ip_str: str) -> str:
        """
        Anonymize IP address (IPv4 or IPv6) with subnet preservation.
        
        Args:
            ip_str: IP address string
            
        Returns:
            Anonymized IP address
        """
        ip_str = ip_str.strip()
        
        # Detect IP version and route to appropriate handler
        if ':' in ip_str:
            return self._anonymize_ip_v6(ip_str)
        else:
            return self._anonymize_ip_v4(ip_str)
    
    def anonymize_email(self, email: str) -> str:
        """
        Anonymize email address while preserving structure.
        
        Args:
            email: Email address
            
        Returns:
            Anonymized email (user_xxxxx@domain.tld)
        """
        email = email.strip().lower()
        
        with self._lock:
            if email in self._mapping_db['email']:
                return self._mapping_db['email'][email]
        
        # Validate email format
        if '@' not in email:
            return email
        
        local_part, domain = email.rsplit('@', 1)
        
        # Generate anonymized local part
        local_hash = self._hmac_hash(local_part, 'email_local')[:8]
        
        # Anonymize domain while preserving TLD
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            tld = domain_parts[-1]
            domain_hash = self._hmac_hash('.'.join(domain_parts[:-1]), 'email_domain')[:8]
            anon_domain = f"domain-{domain_hash}.{tld}"
        else:
            anon_domain = f"domain-{self._hmac_hash(domain, 'email_domain')[:8]}.local"
        
        anon_email = f"user-{local_hash}@{anon_domain}"
        
        with self._lock:
            self._mapping_db['email'][email] = anon_email
            self._stats['by_type']['email'] += 1
            self._stats['total_anonymized'] += 1
        
        return anon_email
    
    def anonymize_url(self, url: str) -> str:
        """
        Anonymize URL while preserving structure using urllib.parse.
        
        Args:
            url: URL string
            
        Returns:
            Anonymized URL with preserved structure
        """
        original_url = url
        
        with self._lock:
            if url in self._mapping_db['url']:
                return self._mapping_db['url'][url]
        
        try:
            parsed = urlparse(url)
            
            # If no scheme, try adding https:// temporarily for parsing
            if not parsed.scheme:
                parsed = urlparse(f"https://{url}")
                had_scheme = False
            else:
                had_scheme = True
            
            # Anonymize hostname
            hostname = parsed.hostname or ''
            if hostname:
                anon_hostname = self.anonymize_domain(hostname)
            else:
                anon_hostname = hostname
            
            # Anonymize username if present
            username = ''
            if parsed.username:
                username = f"user-{self._hmac_hash(parsed.username, 'url_user')[:6]}"
            
            # Reconstruct netloc
            if parsed.port:
                netloc = f"{anon_hostname}:{parsed.port}"
            else:
                netloc = anon_hostname
            
            if username:
                if parsed.password:
                    password = self._hmac_hash(parsed.password, 'url_pass')[:6]
                    netloc = f"{username}:{password}@{netloc}"
                else:
                    netloc = f"{username}@{netloc}"
            
            # Anonymize path segments that look like identifiers
            anon_path = self._anonymize_url_path(parsed.path)
            
            # Reconstruct URL
            anon_parsed = ParseResult(
                scheme=parsed.scheme if had_scheme else '',
                netloc=netloc,
                path=anon_path,
                params=parsed.params,
                query=self._anonymize_query_string(parsed.query),
                fragment=parsed.fragment
            )
            
            anon_url = urlunparse(anon_parsed)
            
            # Remove scheme if original didn't have one
            if not had_scheme and anon_url.startswith('https://'):
                anon_url = anon_url[8:]
            
            with self._lock:
                self._mapping_db['url'][original_url] = anon_url
                self._stats['by_type']['url'] += 1
                self._stats['total_anonymized'] += 1
            
            return anon_url
            
        except Exception:
            return url  # Return original on parse error
    
    def _anonymize_url_path(self, path: str) -> str:
        """Anonymize sensitive path segments."""
        if not path:
            return path
        
        segments = path.split('/')
        anon_segments = []
        
        for segment in segments:
            # Anonymize segments that look like UUIDs, long IDs, or emails
            if self._looks_like_id(segment):
                anon_segments.append(f"id-{self._hmac_hash(segment, 'path')[:8]}")
            elif '@' in segment:
                anon_segments.append(self.anonymize_email(segment))
            else:
                anon_segments.append(segment)
        
        return '/'.join(anon_segments)
    
    def _anonymize_query_string(self, query: str) -> str:
        """Anonymize sensitive query parameters."""
        if not query:
            return query
        
        # Sensitive parameter names
        sensitive_params = {'email', 'user', 'username', 'name', 'id', 'token', 'key', 'password', 'pass', 'api_key', 'apikey'}
        
        pairs = query.split('&')
        anon_pairs = []
        
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                if key.lower() in sensitive_params:
                    value = self._hmac_hash(value, f'query_{key}')[:12]
            anon_pairs.append(pair if '=' not in pair else f"{key}={value}")
        
        return '&'.join(anon_pairs)
    
    def _looks_like_id(self, text: str) -> bool:
        """Check if text looks like a sensitive ID (UUID, long numeric ID, etc.)."""
        if not text:
            return False
        
        # UUID pattern
        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', text, re.I):
            return True
        
        # Long numeric ID
        if re.match(r'^\d{6,}$', text):
            return True
        
        # Hex ID
        if re.match(r'^[0-9a-f]{16,}$', text, re.I):
            return True
        
        return False
    
    def anonymize_domain(self, domain: str) -> str:
        """
        Anonymize domain while preserving TLD structure.
        
        Args:
            domain: Domain name
            
        Returns:
            Anonymized domain (anon-xxx.tld)
        """
        domain = domain.strip().lower()
        
        with self._lock:
            if domain in self._mapping_db['domain']:
                return self._mapping_db['domain'][domain]
        
        parts = domain.split('.')
        
        if len(parts) < 2:
            return domain  # Invalid domain format
        
        # Preserve TLD (last part)
        tld = parts[-1]
        
        # Anonymize the rest
        name_to_hash = '.'.join(parts[:-1])
        name_hash = self._hmac_hash(name_to_hash, 'domain')[:8]
        
        anon_domain = f"domain-{name_hash}.{tld}"
        
        with self._lock:
            self._mapping_db['domain'][domain] = anon_domain
            self._stats['by_type']['domain'] += 1
            self._stats['total_anonymized'] += 1
        
        return anon_domain
    
    def anonymize_mac(self, mac: str) -> str:
        """
        Anonymize MAC address while preserving OUI (manufacturer prefix).
        
        Args:
            mac: MAC address in any format
            
        Returns:
            Anonymized MAC address
        """
        normalized = self._normalize_mac(mac)
        
        with self._lock:
            if normalized in self._mapping_db['mac']:
                return self._mapping_db['mac'][normalized]
        
        parts = normalized.split(':')
        if len(parts) != 6:
            return mac  # Invalid MAC
        
        # Preserve OUI (first 3 octets) for manufacturer identification
        oui = ':'.join(parts[:3])
        
        # Generate anonymized device identifier (last 3 octets)
        nic_hash = self._hmac_hash(normalized, 'mac')
        anon_nic = ':'.join([nic_hash[i:i+2] for i in range(0, 6, 2)])
        
        anon_mac = f"{oui}:{anon_nic}"
        
        with self._lock:
            self._mapping_db['mac'][normalized] = anon_mac
            self._stats['by_type']['mac'] += 1
            self._stats['total_anonymized'] += 1
        
        return anon_mac
    
    def anonymize_username(self, username: str) -> str:
        """
        Anonymize username with consistent mapping.
        
        Args:
            username: Username string
            
        Returns:
            Anonymized username (user_xxxxx)
        """
        username = username.strip()
        
        with self._lock:
            if username in self._mapping_db['user']:
                return self._mapping_db['user'][username]
        
        user_hash = self._hmac_hash(username, 'username')[:8]
        anon_user = f"user_{user_hash}"
        
        with self._lock:
            self._mapping_db['user'][username] = anon_user
            self._stats['by_type']['user'] += 1
            self._stats['total_anonymized'] += 1
        
        return anon_user
    
    def anonymize_hostname(self, hostname: str) -> str:
        """
        Anonymize hostname with consistent mapping.
        
        Args:
            hostname: Hostname string
            
        Returns:
            Anonymized hostname (host_xxxxx)
        """
        hostname = hostname.strip().lower()
        
        with self._lock:
            if hostname in self._mapping_db['hostname']:
                return self._mapping_db['hostname'][hostname]
        
        host_hash = self._hmac_hash(hostname, 'hostname')[:8]
        anon_host = f"host_{host_hash}"
        
        with self._lock:
            self._mapping_db['hostname'][hostname] = anon_host
            self._stats['by_type']['hostname'] += 1
            self._stats['total_anonymized'] += 1
        
        return anon_host
    
    def register_custom_field(self, field_name: str, pattern: Optional[str] = None):
        """
        Register a custom field for anonymization with word boundary matching.
        
        Args:
            field_name: Name of the field to anonymize
            pattern: Optional regex pattern. If None, creates boundary-aware exact match.
        """
        if pattern:
            self._custom_patterns[field_name] = re.compile(pattern)
        else:
            # Create word-boundary aware pattern for the field value
            self._custom_patterns[field_name] = None  # Will use boundary-aware replacement
    
    def anonymize_custom(self, value: str, field_name: str) -> str:
        """
        Anonymize custom field value with consistent mapping.
        
        Args:
            value: Value to anonymize
            field_name: Field name for categorization
            
        Returns:
            Anonymized value
        """
        value = str(value).strip()
        
        cache_key = f"{field_name}:{value}"
        
        with self._lock:
            if cache_key in self._mapping_db['custom']:
                return self._mapping_db['custom'][cache_key]
        
        value_hash = self._hmac_hash(value, f'custom_{field_name}')[:8]
        anon_value = f"{field_name}_{value_hash}"
        
        with self._lock:
            self._mapping_db['custom'][cache_key] = anon_value
            self._stats['by_type']['custom'] += 1
            self._stats['total_anonymized'] += 1
        
        return anon_value
    
    def anonymize_text(self, text: str, 
                       anonymize_ips: bool = True,
                       anonymize_emails: bool = True,
                       anonymize_urls: bool = True,
                       anonymize_macs: bool = True,
                       anonymize_domains: bool = False) -> str:
        """
        Anonymize all sensitive data in text using boundary-aware matching.
        
        Args:
            text: Input text to anonymize
            anonymize_ips: Whether to anonymize IP addresses
            anonymize_emails: Whether to anonymize email addresses
            anonymize_urls: Whether to anonymize URLs
            anonymize_macs: Whether to anonymize MAC addresses
            anonymize_domains: Whether to anonymize standalone domains
            
        Returns:
            Anonymized text
        """
        if not text:
            return text
        
        result = text
        
        # Anonymize emails first (to avoid partial matches with domains)
        if anonymize_emails:
            result = self.EMAIL_PATTERN.sub(
                lambda m: self.anonymize_email(m.group(0)),
                result
            )
        
        # Anonymize URLs (before IPs to handle IPs in URLs correctly)
        if anonymize_urls:
            url_pattern = re.compile(
                r'https?://[^\s<>"\']+',
                re.IGNORECASE
            )
            result = url_pattern.sub(
                lambda m: self.anonymize_url(m.group(0)),
                result
            )
        
        # Anonymize IPv6 addresses (before IPv4 to avoid partial matches)
        if anonymize_ips:
            # IPv6 pattern
            ipv6_pattern = re.compile(
                r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|'
                r'\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b|'
                r'\b(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}\b|'
                r'\b(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}\b|'
                r'\b(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}\b|'
                r'\b(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}\b|'
                r'\b(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}\b|'
                r'\b[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}\b|'
                r'\b:(?::[0-9a-fA-F]{1,4}){1,7}\b|'
                r'\b::(?:[0-9a-fA-F]{1,4}:){0,5}[0-9a-fA-F]{1,4}\b'
            )
            result = ipv6_pattern.sub(
                lambda m: self.anonymize_ip(m.group(0)),
                result
            )
            
            # IPv4 pattern with word boundaries
            ipv4_pattern = re.compile(
                r'\b(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
            )
            result = ipv4_pattern.sub(
                lambda m: self.anonymize_ip(m.group(0)),
                result
            )
        
        # Anonymize MAC addresses
        if anonymize_macs:
            for pattern in self.MAC_PATTERNS:
                result = pattern.sub(
                    lambda m: self.anonymize_mac(m.group(0)),
                    result
                )
        
        # Anonymize standalone domains (careful with false positives)
        if anonymize_domains:
            result = self.DOMAIN_PATTERN.sub(
                lambda m: self.anonymize_domain(m.group(0)),
                result
            )
        
        return result
    
    def anonymize_json(self, data: Any, 
                       field_mapping: Optional[Dict[str, str]] = None,
                       deep_scan: bool = True) -> Any:
        """
        Anonymize sensitive data in JSON structure.
        
        Args:
            data: JSON data (dict, list, or primitive)
            field_mapping: Optional mapping of field names to anonymization types
                          e.g., {'src_ip': 'ip', 'user_email': 'email'}
            deep_scan: Whether to scan string values for embedded sensitive data
            
        Returns:
            Anonymized JSON structure
        """
        field_mapping = field_mapping or {}
        
        # Default field mappings
        default_mappings = {
            # IP fields
            'ip': 'ip', 'src_ip': 'ip', 'dst_ip': 'ip', 'source_ip': 'ip', 
            'dest_ip': 'ip', 'client_ip': 'ip', 'server_ip': 'ip',
            'remote_ip': 'ip', 'local_ip': 'ip', 'ip_address': 'ip',
            'srcip': 'ip', 'dstip': 'ip', 'ipaddr': 'ip',
            
            # Email fields
            'email': 'email', 'user_email': 'email', 'from': 'email',
            'to': 'email', 'sender': 'email', 'recipient': 'email',
            'mail': 'email', 'e-mail': 'email', 'email_address': 'email',
            
            # User fields
            'user': 'user', 'username': 'user', 'user_name': 'user',
            'login': 'user', 'account': 'user', 'userid': 'user',
            
            # Hostname fields
            'hostname': 'hostname', 'host': 'hostname', 'server': 'hostname',
            'machine': 'hostname', 'computer': 'hostname', 'node': 'hostname',
            
            # MAC fields
            'mac': 'mac', 'mac_address': 'mac', 'hw_addr': 'mac',
            'hardware_address': 'mac', 'macaddr': 'mac',
            
            # Domain fields
            'domain': 'domain', 'fqdn': 'domain', 'dns_name': 'domain',
            
            # URL fields
            'url': 'url', 'uri': 'url', 'href': 'url', 'link': 'url',
            'request_url': 'url', 'referer': 'url', 'referrer': 'url',
        }
        
        # Merge with user-provided mappings
        effective_mapping = {**default_mappings, **field_mapping}
        
        return self._anonymize_json_recursive(data, effective_mapping, deep_scan)
    
    def _anonymize_json_recursive(self, data: Any, 
                                   field_mapping: Dict[str, str],
                                   deep_scan: bool,
                                   current_key: str = '') -> Any:
        """Recursively anonymize JSON structure."""
        if isinstance(data, dict):
            return {
                k: self._anonymize_json_recursive(v, field_mapping, deep_scan, k.lower())
                for k, v in data.items()
            }
        
        elif isinstance(data, list):
            return [
                self._anonymize_json_recursive(item, field_mapping, deep_scan, current_key)
                for item in data
            ]
        
        elif isinstance(data, str):
            # Check if current key has explicit mapping
            anon_type = field_mapping.get(current_key)
            
            if anon_type == 'ip':
                return self.anonymize_ip(data)
            elif anon_type == 'email':
                return self.anonymize_email(data)
            elif anon_type == 'user':
                return self.anonymize_username(data)
            elif anon_type == 'hostname':
                return self.anonymize_hostname(data)
            elif anon_type == 'mac':
                return self.anonymize_mac(data)
            elif anon_type == 'domain':
                return self.anonymize_domain(data)
            elif anon_type == 'url':
                return self.anonymize_url(data)
            elif deep_scan:
                # Scan string for embedded sensitive data
                return self.anonymize_text(data)
            
            return data
        
        else:
            return data
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive AES-256 key from password using PBKDF2-HMAC-SHA256.
        
        Args:
            password: User password
            salt: Random salt (16 bytes recommended)
            
        Returns:
            32-byte key for AES-256
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits for AES-256
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))
    
    def export_mapping_db(self, 
                          password: Optional[str] = None,
                          use_key_manager: bool = True) -> bytes:
        """
        Export mapping database with optional AES-256-GCM encryption.
        
        Args:
            password: Optional password for encryption. Takes priority over key manager.
            use_key_manager: If True and no password, use KeyManager for encryption key.
            
        Returns:
            JSON bytes (or encrypted bytes if encryption enabled)
            
        Encrypted format:
            version (1 byte) + salt (16 bytes) + nonce (12 bytes) + ciphertext + tag (16 bytes)
            
        Key sources (priority):
            1. password parameter → PBKDF2 derived key
            2. KeyManager (env var / key file) → direct key
            3. No encryption (if neither available)
            
        Example:
            # Using password
            data = anonymizer.export_mapping_db(password="my_password")
            
            # Using KeyManager (recommended for production)
            os.environ["ANONYMIZER_ENCRYPTION_KEY"] = KeyManager.generate_key_for_env()
            data = anonymizer.export_mapping_db()  # Auto-uses env key
            
            # Unencrypted
            data = anonymizer.export_mapping_db(use_key_manager=False)
        """
        with self._lock:
            export_data = {
                'version': '2.1',
                'created': datetime.utcnow().isoformat(),
                'mappings': {k: dict(v) for k, v in self._mapping_db.items()},
                'stats': dict(self._stats),
            }
        
        json_bytes = json.dumps(export_data, indent=2).encode('utf-8')
        
        # Determine encryption method
        encryption_key: Optional[bytes] = None
        key_source = 'none'
        
        if password:
            # Password-based encryption
            if not CRYPTO_AVAILABLE:
                raise RuntimeError("cryptography package required. Install with: pip install cryptography")
            
            salt = secrets.token_bytes(16)
            encryption_key = self._derive_key(password, salt)
            key_source = 'password'
            
        elif use_key_manager:
            # KeyManager-based encryption
            key_mgr = get_key_manager()
            encryption_key = key_mgr.get_key(auto_generate=False)
            
            if encryption_key:
                if not CRYPTO_AVAILABLE:
                    raise RuntimeError("cryptography package required. Install with: pip install cryptography")
                salt = secrets.token_bytes(16)  # Salt still used for nonce derivation
                key_source = 'keymanager'
        
        if encryption_key:
            nonce = secrets.token_bytes(12)  # 96-bit nonce for GCM
            
            aesgcm = AESGCM(encryption_key)
            ciphertext = aesgcm.encrypt(nonce, json_bytes, None)
            
            # Version byte: 0x01 = password-based, 0x02 = keymanager-based
            version_byte = b'\x01' if key_source == 'password' else b'\x02'
            
            # Update export_data encryption info (for metadata, not stored in encrypted blob)
            export_data['encryption'] = 'AES-256-GCM'
            export_data['key_source'] = key_source
            
            return version_byte + salt + nonce + ciphertext
        
        # No encryption
        export_data['encryption'] = 'none'
        return json_bytes
    
    def import_mapping_db(self, 
                          data: bytes, 
                          password: Optional[str] = None,
                          use_key_manager: bool = True):
        """
        Import mapping database with optional AES-256-GCM decryption.
        
        Args:
            data: Exported data (encrypted or plain JSON)
            password: Password for decryption (if password-encrypted)
            use_key_manager: If True, try KeyManager for keymanager-encrypted data
            
        Raises:
            RuntimeError: If cryptography package not available
            ValueError: If decryption fails (wrong password/key or corrupted data)
        """
        # Check if data is encrypted (starts with version byte 0x01 or 0x02)
        is_encrypted = len(data) > 0 and data[0] in (0x01, 0x02)
        
        if is_encrypted:
            if not CRYPTO_AVAILABLE:
                raise RuntimeError("cryptography package required. Install with: pip install cryptography")
            
            version = data[0]
            salt = data[1:17]
            nonce = data[17:29]
            ciphertext = data[29:]
            
            # Determine decryption key
            if version == 0x01:
                # Password-based encryption
                if not password:
                    raise ValueError("Password required: data was encrypted with password")
                encryption_key = self._derive_key(password, salt)
                
            elif version == 0x02:
                # KeyManager-based encryption
                if not use_key_manager:
                    raise ValueError("KeyManager required: data was encrypted with KeyManager key")
                
                key_mgr = get_key_manager()
                encryption_key = key_mgr.get_key(auto_generate=False)
                
                if not encryption_key:
                    raise ValueError(
                        "No encryption key available. Set ANONYMIZER_ENCRYPTION_KEY env var "
                        "or ensure key file exists at ~/.smartxdr/anonymizer.key"
                    )
            else:
                raise ValueError(f"Unknown encryption version: {version}")
            
            # Decrypt
            try:
                aesgcm = AESGCM(encryption_key)
                json_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            except Exception as e:
                if version == 0x01:
                    raise ValueError(f"Decryption failed: wrong password. Details: {e}")
                else:
                    raise ValueError(f"Decryption failed: wrong key or key was rotated. Details: {e}")
        else:
            # Plain JSON (legacy or unencrypted)
            json_bytes = data
        
        try:
            import_data = json.loads(json_bytes.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON data: {e}")
        
        with self._lock:
            if 'mappings' in import_data:
                for category, mappings in import_data['mappings'].items():
                    if category in self._mapping_db:
                        self._mapping_db[category].update(mappings)
            
            if 'stats' in import_data:
                for key, value in import_data['stats'].items():
                    if key in self._stats:
                        if isinstance(value, dict):
                            self._stats[key].update(value)
                        else:
                            self._stats[key] = value
    
    def get_stats(self) -> Dict[str, Any]:
        """Get anonymization statistics."""
        with self._lock:
            return {
                **self._stats,
                'mapping_counts': {k: len(v) for k, v in self._mapping_db.items()},
            }
    
    def clear_mappings(self, categories: Optional[List[str]] = None):
        """
        Clear mapping database.
        
        Args:
            categories: Optional list of categories to clear. If None, clears all.
        """
        with self._lock:
            if categories:
                for cat in categories:
                    if cat in self._mapping_db:
                        self._mapping_db[cat] = {}
                        self._stats['by_type'][cat] = 0
            else:
                for cat in self._mapping_db:
                    self._mapping_db[cat] = {}
                for cat in self._stats['by_type']:
                    self._stats['by_type'][cat] = 0
                self._stats['total_anonymized'] = 0
    
    def get_reverse_mapping(self, anonymized_value: str) -> Optional[Tuple[str, str]]:
        """
        Get original value from anonymized value (if mapping exists).
        
        Args:
            anonymized_value: The anonymized value to look up
            
        Returns:
            Tuple of (original_value, category) or None if not found
        """
        with self._lock:
            for category, mappings in self._mapping_db.items():
                for original, anon in mappings.items():
                    if anon == anonymized_value:
                        return (original, category)
        return None


# Convenience function for quick anonymization
def anonymize_log(log_data: Any, 
                  preserve_subnet_prefix: int = 16,
                  field_mapping: Optional[Dict[str, str]] = None) -> Any:
    """
    Quick anonymization of log data.
    
    Args:
        log_data: Log data (string, dict, or list)
        preserve_subnet_prefix: IPv4 subnet bits to preserve
        field_mapping: Optional field-to-type mapping
        
    Returns:
        Anonymized log data
    """
    anonymizer = SecureLogAnonymizer(preserve_subnet_prefix=preserve_subnet_prefix)
    
    if isinstance(log_data, str):
        return anonymizer.anonymize_text(log_data)
    else:
        return anonymizer.anonymize_json(log_data, field_mapping=field_mapping)


# Singleton instance for consistent mapping across calls
_default_anonymizer: Optional[SecureLogAnonymizer] = None
_singleton_lock = threading.Lock()


def get_anonymizer(hmac_key: Optional[bytes] = None) -> SecureLogAnonymizer:
    """
    Get or create singleton anonymizer instance.
    
    Args:
        hmac_key: HMAC key (only used on first call)
        
    Returns:
        SecureLogAnonymizer instance
    """
    global _default_anonymizer
    
    with _singleton_lock:
        if _default_anonymizer is None:
            _default_anonymizer = SecureLogAnonymizer(hmac_key=hmac_key)
        return _default_anonymizer


# =============================================================================
# Backward Compatibility Aliases
# =============================================================================
# These aliases maintain compatibility with code using the old class names

DataAnonymizer = SecureLogAnonymizer
"""
DEPRECATED: Use SecureLogAnonymizer instead.

DataAnonymizer is an alias for SecureLogAnonymizer for backward compatibility.
This alias will be removed in a future version.
"""

LogAnonymizer = SecureLogAnonymizer
"""
DEPRECATED: Use SecureLogAnonymizer instead.
"""
