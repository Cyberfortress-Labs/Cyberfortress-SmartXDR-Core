"""
Data Sanitization Layer for SmartXDR
Zero-Knowledge approach: Tokenization, Hashing, Private Mapping Database
Ensures AI/external services only receive anonymized data
"""

import hashlib
import ipaddress
import re
import secrets
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
import json


class DataAnonymizer:
    """
    Data sanitization layer implementing Zero-Knowledge approach
    - Tokenization: Replace sensitive values with tokens
    - Hashing: One-way hash for consistent anonymization
    - Private Mapping: Maintain reverse lookup database
    """
    
    def __init__(self, salt: Optional[str] = None):
        """
        Initialize anonymizer with optional salt for hashing
        
        Args:
            salt: Custom salt for hashing (if None, generates random)
        """
        self.salt = salt or secrets.token_hex(32)
        self._mapping_db: Dict[str, Dict[str, Any]] = {
            'ip': {},
            'user': {},
            'hostname': {},
            'domain': {},
            'url': {},
            'email': {},
            'hash': {},
            'mac': {}
        }
        self._reverse_mapping: Dict[str, str] = {}
        
    # ==================== IP ADDRESS ANONYMIZATION ====================
    
    def _is_private_ip(self, ip: str) -> bool:
        """Check if IP is private/internal"""
        try:
            ip_obj = ipaddress.ip_address(ip)
            return ip_obj.is_private
        except ValueError:
            return False
    
    def _anonymize_ip_tokenization(self, ip: str) -> str:
        """
        Tokenize IP with format-preserving token
        Example: 192.168.85.112 -> TKN-IP-a3f7b2c9
        """
        if ip in self._mapping_db['ip']:
            return self._mapping_db['ip'][ip]['token']
        
        # Generate 8-char token
        token = f"TKN-IP-{secrets.token_hex(4)}"
        
        self._mapping_db['ip'][ip] = {
            'token': token,
            'is_private': self._is_private_ip(ip),
            'first_seen': datetime.utcnow().isoformat(),
            'occurrences': 1
        }
        self._reverse_mapping[token] = ip
        
        return token
    
    def _anonymize_ip_hashing(self, ip: str) -> str:
        """
        Hash IP with SHA256 (one-way, consistent)
        Example: 192.168.85.112 -> HSH-IP-7f3a9b2c1d4e5f6a
        """
        ip_hash = hashlib.sha256(f"{ip}{self.salt}".encode()).hexdigest()[:16]
        hashed = f"HSH-IP-{ip_hash}"
        
        if ip not in self._mapping_db['ip']:
            self._mapping_db['ip'][ip] = {
                'hash': hashed,
                'is_private': self._is_private_ip(ip),
                'first_seen': datetime.utcnow().isoformat(),
                'occurrences': 1
            }
        else:
            self._mapping_db['ip'][ip]['occurrences'] += 1
            
        return hashed
    
    def _anonymize_ip_subnet_preserving(self, ip: str) -> str:
        """
        Preserve subnet structure for network analysis
        Example: 192.168.85.112 -> 10.0.1.X (keeps /24 pattern)
        """
        try:
            ip_obj = ipaddress.ip_address(ip)
            octets = str(ip_obj).split('.')
            
            if self._is_private_ip(ip):
                # Map private subnets consistently
                subnet_key = '.'.join(octets[:3])
                if subnet_key not in self._mapping_db['ip']:
                    # Generate pseudo-random but consistent subnet
                    subnet_hash = int(hashlib.sha256(f"{subnet_key}{self.salt}".encode()).hexdigest()[:4], 16)
                    pseudo_subnet = f"10.{(subnet_hash % 254) + 1}.{(subnet_hash // 254) % 254}"
                    self._mapping_db['ip'][subnet_key] = {'pseudo_subnet': pseudo_subnet}
                
                pseudo = self._mapping_db['ip'][subnet_key]['pseudo_subnet']
                # Keep host part for pattern analysis
                return f"{pseudo}.{octets[3]}"
            else:
                # Public IPs: full anonymization
                return self._anonymize_ip_hashing(ip)
                
        except ValueError:
            return ip  # Invalid IP, return as-is
    
    def anonymize_ip(self, ip: str, method: str = 'token') -> str:
        """
        Anonymize IP address
        
        Args:
            ip: IP address to anonymize
            method: 'token' (reversible), 'hash' (one-way), 'subnet' (preserve structure)
        
        Returns:
            Anonymized IP
        """
        if method == 'token':
            return self._anonymize_ip_tokenization(ip)
        elif method == 'hash':
            return self._anonymize_ip_hashing(ip)
        elif method == 'subnet':
            return self._anonymize_ip_subnet_preserving(ip)
        else:
            raise ValueError(f"Unknown method: {method}")
    
    # ==================== USERNAME ANONYMIZATION ====================
    
    def anonymize_username(self, username: str, method: str = 'token') -> str:
        """
        Anonymize username
        
        Args:
            username: Username to anonymize
            method: 'token' or 'hash'
        
        Returns:
            Anonymized username
        """
        if username in self._mapping_db['user']:
            return self._mapping_db['user'][username].get(method, username)
        
        if method == 'token':
            token = f"USER-{secrets.token_hex(4)}"
            self._mapping_db['user'][username] = {
                'token': token,
                'first_seen': datetime.utcnow().isoformat()
            }
            self._reverse_mapping[token] = username
            return token
        
        elif method == 'hash':
            user_hash = hashlib.sha256(f"{username}{self.salt}".encode()).hexdigest()[:12]
            hashed = f"USER-{user_hash}"
            self._mapping_db['user'][username] = {
                'hash': hashed,
                'first_seen': datetime.utcnow().isoformat()
            }
            return hashed
        
        return username
    
    # ==================== HOSTNAME ANONYMIZATION ====================
    
    def anonymize_hostname(self, hostname: str, method: str = 'token') -> str:
        """
        Anonymize hostname
        
        Args:
            hostname: Hostname to anonymize
            method: 'token' or 'hash'
        
        Returns:
            Anonymized hostname
        """
        if hostname in self._mapping_db['hostname']:
            return self._mapping_db['hostname'][hostname].get(method, hostname)
        
        if method == 'token':
            token = f"HOST-{secrets.token_hex(4)}"
            self._mapping_db['hostname'][hostname] = {
                'token': token,
                'first_seen': datetime.utcnow().isoformat()
            }
            self._reverse_mapping[token] = hostname
            return token
        
        elif method == 'hash':
            host_hash = hashlib.sha256(f"{hostname}{self.salt}".encode()).hexdigest()[:12]
            hashed = f"HOST-{host_hash}"
            self._mapping_db['hostname'][hostname] = {
                'hash': hashed,
                'first_seen': datetime.utcnow().isoformat()
            }
            return hashed
        
        return hostname
    
    # ==================== DOMAIN/URL ANONYMIZATION ====================
    
    def anonymize_domain(self, domain: str, method: str = 'hash') -> str:
        """
        Anonymize domain name
        
        Args:
            domain: Domain to anonymize
            method: 'hash' (recommended for domains)
        
        Returns:
            Anonymized domain
        """
        if domain in self._mapping_db['domain']:
            return self._mapping_db['domain'][domain]['hash']
        
        domain_hash = hashlib.sha256(f"{domain}{self.salt}".encode()).hexdigest()[:16]
        hashed = f"domain-{domain_hash}.anon"
        
        self._mapping_db['domain'][domain] = {
            'hash': hashed,
            'first_seen': datetime.utcnow().isoformat()
        }
        
        return hashed
    
    def anonymize_url(self, url: str) -> str:
        """
        Anonymize URL while preserving structure
        Example: http://192.168.85.112/admin -> http://TKN-IP-xxx/admin
        """
        # Extract and anonymize IP/domain
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        domain_pattern = r'(?:https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        
        # Replace IPs
        url = re.sub(ip_pattern, lambda m: self.anonymize_ip(m.group()), url)
        
        # Replace domains (but keep path structure)
        url = re.sub(domain_pattern, lambda m: self.anonymize_domain(m.group(1)), url)
        
        return url
    
    # ==================== EMAIL ANONYMIZATION ====================
    
    def anonymize_email(self, email: str) -> str:
        """
        Anonymize email address
        Example: admin@company.com -> USER-xxx@DOMAIN-yyy
        """
        if '@' not in email:
            return email
        
        if email in self._mapping_db['email']:
            return self._mapping_db['email'][email]['token']
        
        local, domain = email.split('@', 1)
        local_token = self.anonymize_username(local, method='hash')[:12]
        domain_token = self.anonymize_domain(domain)
        
        anon_email = f"{local_token}@{domain_token}"
        
        self._mapping_db['email'][email] = {
            'token': anon_email,
            'first_seen': datetime.utcnow().isoformat()
        }
        
        return anon_email
    
    # ==================== BATCH PROCESSING ====================
    
    def anonymize_log_event(self, log_event: Dict[str, Any], 
                           fields_to_anonymize: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Anonymize entire log event
        
        Args:
            log_event: Raw log event dictionary
            fields_to_anonymize: List of field names to anonymize (auto-detect if None)
        
        Returns:
            Anonymized log event
        """
        anonymized = log_event.copy()
        
        # Default sensitive fields
        if fields_to_anonymize is None:
            fields_to_anonymize = [
                'src_ip', 'source.ip', 'client_ip', 'remote_addr',
                'dst_ip', 'dest_ip', 'destination.ip',
                'user', 'username', 'user.name',
                'hostname', 'host', 'host.name',
                'email', 'user.email',
                'url', 'request.url',
                'domain'
            ]
        
        # Recursively anonymize fields
        def anonymize_recursive(obj, parent_key=''):
            if isinstance(obj, dict):
                result = {}
                for key, value in obj.items():
                    full_key = f"{parent_key}.{key}" if parent_key else key
                    
                    # Check if field should be anonymized
                    if any(field in full_key for field in fields_to_anonymize):
                        if 'ip' in full_key.lower() and isinstance(value, str):
                            result[key] = self.anonymize_ip(value, method='token')
                        elif 'user' in full_key.lower() and isinstance(value, str):
                            result[key] = self.anonymize_username(value, method='token')
                        elif 'host' in full_key.lower() and isinstance(value, str):
                            result[key] = self.anonymize_hostname(value, method='token')
                        elif 'email' in full_key.lower() and isinstance(value, str):
                            result[key] = self.anonymize_email(value)
                        elif 'url' in full_key.lower() and isinstance(value, str):
                            result[key] = self.anonymize_url(value)
                        elif 'domain' in full_key.lower() and isinstance(value, str):
                            result[key] = self.anonymize_domain(value)
                        else:
                            result[key] = value
                    else:
                        result[key] = anonymize_recursive(value, full_key)
                return result
            elif isinstance(obj, list):
                return [anonymize_recursive(item, parent_key) for item in obj]
            else:
                return obj
        
        return anonymize_recursive(anonymized)
    
    # ==================== REVERSE MAPPING (De-anonymization) ====================
    
    def deanonymize(self, token: str) -> Optional[str]:
        """
        Reverse lookup: token -> original value
        Only works with tokenization method (not hashing)
        
        Args:
            token: Anonymized token (e.g., TKN-IP-xxx)
        
        Returns:
            Original value or None if not found
        """
        return self._reverse_mapping.get(token)
    
    def get_mapping_stats(self) -> Dict[str, int]:
        """Get statistics about anonymized data"""
        return {
            'total_ips': len(self._mapping_db['ip']),
            'total_users': len(self._mapping_db['user']),
            'total_hostnames': len(self._mapping_db['hostname']),
            'total_domains': len(self._mapping_db['domain']),
            'total_emails': len(self._mapping_db['email']),
            'total_reversible_mappings': len(self._reverse_mapping)
        }
    
    # ==================== PERSISTENCE ====================
    
    def export_mapping_db(self, filepath: str):
        """Export mapping database to file (for backup/restore)"""
        with open(filepath, 'w') as f:
            json.dump({
                'salt': self.salt,
                'mapping_db': self._mapping_db,
                'reverse_mapping': self._reverse_mapping,
                'exported_at': datetime.utcnow().isoformat()
            }, f, indent=2)
    
    def import_mapping_db(self, filepath: str):
        """Import mapping database from file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.salt = data['salt']
            self._mapping_db = data['mapping_db']
            self._reverse_mapping = data['reverse_mapping']


# ==================== FACTORY FUNCTIONS ====================

_global_anonymizer: Optional[DataAnonymizer] = None

def get_anonymizer(salt: Optional[str] = None) -> DataAnonymizer:
    """
    Get singleton anonymizer instance
    
    Args:
        salt: Custom salt (only used on first call)
    
    Returns:
        DataAnonymizer instance
    """
    global _global_anonymizer
    if _global_anonymizer is None:
        _global_anonymizer = DataAnonymizer(salt=salt)
    return _global_anonymizer


# ==================== CONVENIENCE FUNCTIONS ====================

def anonymize_suricata_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Anonymize Suricata EVE-JSON alert
    
    Args:
        alert: Suricata alert dict
    
    Returns:
        Anonymized alert
    """
    anonymizer = get_anonymizer()
    
    # Common Suricata fields to anonymize
    fields = [
        'src_ip', 'dest_ip', 'src_port', 'dest_port',
        'http.hostname', 'dns.rrname', 'tls.sni',
        'smtp.mail_from', 'smtp.rcpt_to'
    ]
    
    return anonymizer.anonymize_log_event(alert, fields_to_anonymize=fields)


def anonymize_zeek_log(log: Dict[str, Any]) -> Dict[str, Any]:
    """
    Anonymize Zeek log entry
    
    Args:
        log: Zeek log dict
    
    Returns:
        Anonymized log
    """
    anonymizer = get_anonymizer()
    
    # Common Zeek conn.log fields
    fields = [
        'id.orig_h', 'id.resp_h', 'id.orig_p', 'id.resp_p',
        'host', 'uri', 'username', 'server_name'
    ]
    
    return anonymizer.anonymize_log_event(log, fields_to_anonymize=fields)


def anonymize_wazuh_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Anonymize Wazuh alert
    
    Args:
        alert: Wazuh alert dict
    
    Returns:
        Anonymized alert
    """
    anonymizer = get_anonymizer()
    
    # Wazuh alert fields
    fields = [
        'agent.ip', 'agent.name',
        'data.srcip', 'data.dstip',
        'data.srcuser', 'data.dstuser',
        'predecoder.hostname'
    ]
    
    return anonymizer.anonymize_log_event(alert, fields_to_anonymize=fields)
