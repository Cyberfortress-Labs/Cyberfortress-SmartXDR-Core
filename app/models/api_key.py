"""
API Key Model for SmartXDR
Stores and manages API keys in SQLite database
"""
import sqlite3
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

from app.utils.cryptography import hash_api_key, verify_api_key

logger = logging.getLogger('smartxdr.api_key')
class APIKey:
    """API Key model with database persistence"""
    
    def __init__(self, db_path: str = "data/api_keys.db"):
        self.db_path = db_path
        self._ensure_db()
    
    def _ensure_db(self):
        """Create database and tables if not exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # API Keys table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT UNIQUE NOT NULL,
                key_prefix TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                permissions TEXT NOT NULL,
                rate_limit INTEGER DEFAULT 60,
                enabled BOOLEAN DEFAULT 1,
                expires_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                last_used_at DATETIME,
                usage_count INTEGER DEFAULT 0,
                metadata TEXT
            )
        ''')
        
        # API Key usage logs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_key_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT,
                client_ip TEXT,
                user_agent TEXT,
                status_code INTEGER,
                response_time_ms INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (key_hash) REFERENCES api_keys(key_hash)
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_key_hash ON api_keys(key_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_enabled ON api_keys(enabled)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_expires_at ON api_keys(expires_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_key_hash ON api_key_usage(key_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_created_at ON api_key_usage(created_at)')
        
        conn.commit()
        conn.close()
        
        logger.info(f"✓ API key database initialized: {self.db_path}")
    
    def _hash_key(self, key: str) -> str:
        """Hash API key using Argon2id"""
        return hash_api_key(key)
    
    def generate_key(self, prefix: str = "sxdr") -> str:
        """Generate a new secure API key"""
        random_part = secrets.token_urlsafe(32)
        return f"{prefix}_{random_part}"
    
    def create(
        self,
        name: str,
        permissions: List[str],
        description: str = "",
        rate_limit: int = 60,
        expires_in_days: Optional[int] = None,
        created_by: str = "system",
        prefix: str = "sxdr",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key
        
        Args:
            name: Key name/identifier
            permissions: List of permissions (e.g., ['ai:*', 'enrich:read'])
            description: Optional description
            rate_limit: Requests per minute limit
            expires_in_days: Expiration in days (None = no expiry)
            created_by: Who created this key
            prefix: Key prefix (default: sxdr)
            metadata: Additional metadata (JSON)
        
        Returns:
            {
                'key': 'sxdr_xxx...',  # Only returned once!
                'key_hash': 'abc...',
                'name': '...',
                'permissions': [...],
                ...
            }
        """
        # Generate key
        api_key = self.generate_key(prefix)
        key_hash = self._hash_key(api_key)
        key_prefix = api_key.split('_')[0]
        
        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = (datetime.now() + timedelta(days=expires_in_days)).isoformat()
        
        # Prepare data
        permissions_json = json.dumps(permissions)
        metadata_json = json.dumps(metadata) if metadata else None
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO api_keys (
                    key_hash, key_prefix, name, description, permissions,
                    rate_limit, expires_at, created_by, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                key_hash, key_prefix, name, description, permissions_json,
                rate_limit, expires_at, created_by, metadata_json
            ))
            
            conn.commit()
            key_id = cursor.lastrowid
            
            logger.info(f"✓ Created API key: {name} (id={key_id})")
            
            return {
                'id': key_id,
                'key': api_key,  # ONLY SHOWN ONCE!
                'key_hash': key_hash,
                'key_prefix': key_prefix,
                'name': name,
                'description': description,
                'permissions': permissions,
                'rate_limit': rate_limit,
                'expires_at': expires_at,
                'created_at': datetime.now().isoformat(),
                'created_by': created_by
            }
        
        except sqlite3.IntegrityError:
            logger.error(f"API key already exists: {name}")
            return None
        finally:
            conn.close()
    
    def validate(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Validate API key and return key info
        
        Returns:
            {
                'id': 1,
                'name': 'master',
                'permissions': ['*'],
                'rate_limit': 1000,
                'enabled': True,
                ...
            }
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all enabled keys (Argon2id requires verification, not hash comparison)
        cursor.execute('''
            SELECT * FROM api_keys 
            WHERE enabled = 1
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return None
        
        # Verify API key against each stored hash
        for row in rows:
            if verify_api_key(api_key, row['key_hash']):
                # Check expiration
                if row['expires_at']:
                    expires_at = datetime.fromisoformat(row['expires_at'])
                    if datetime.now() > expires_at:
                        logger.warning(f"API key expired: {row['name']}")
                        return None
                
                # Parse JSON fields
                permissions = json.loads(row['permissions'])
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                
                return {
                    'id': row['id'],
                    'name': row['name'],
                    'description': row['description'],
                    'permissions': permissions,
                    'rate_limit': row['rate_limit'],
                    'enabled': bool(row['enabled']),
                    'expires_at': row['expires_at'],
                    'created_at': row['created_at'],
                    'last_used_at': row['last_used_at'],
                    'usage_count': row['usage_count'],
                    'metadata': metadata
                }
        
        return None
    
    def update_usage(self, api_key: str):
        """Update last_used_at and usage_count"""
        key_hash = self._hash_key(api_key)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE api_keys 
            SET last_used_at = CURRENT_TIMESTAMP,
                usage_count = usage_count + 1
            WHERE key_hash = ?
        ''', (key_hash,))
        
        conn.commit()
        conn.close()
    
    def log_usage(
        self,
        api_key: str,
        endpoint: str,
        method: str = "POST",
        client_ip: str = None,
        user_agent: str = None,
        status_code: int = 200,
        response_time_ms: int = 0
    ):
        """Log API key usage for analytics"""
        key_hash = self._hash_key(api_key)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO api_key_usage (
                key_hash, endpoint, method, client_ip, user_agent,
                status_code, response_time_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (key_hash, endpoint, method, client_ip, user_agent, status_code, response_time_ms))
        
        conn.commit()
        conn.close()
    
    def list_keys(self, include_disabled: bool = False) -> List[Dict[str, Any]]:
        """List all API keys (without raw keys)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if include_disabled:
            cursor.execute('SELECT * FROM api_keys ORDER BY created_at DESC')
        else:
            cursor.execute('SELECT * FROM api_keys WHERE enabled = 1 ORDER BY created_at DESC')
        
        rows = cursor.fetchall()
        conn.close()
        
        keys = []
        for row in rows:
            permissions = json.loads(row['permissions'])
            metadata = json.loads(row['metadata']) if row['metadata'] else {}
            
            keys.append({
                'id': row['id'],
                'key_prefix': row['key_prefix'],
                'name': row['name'],
                'description': row['description'],
                'permissions': permissions,
                'rate_limit': row['rate_limit'],
                'enabled': bool(row['enabled']),
                'expires_at': row['expires_at'],
                'created_at': row['created_at'],
                'created_by': row['created_by'],
                'last_used_at': row['last_used_at'],
                'usage_count': row['usage_count'],
                'metadata': metadata
            })
        
        return keys
    
    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get API key info by name"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM api_keys WHERE name = ?', (name,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        permissions = json.loads(row['permissions'])
        metadata = json.loads(row['metadata']) if row['metadata'] else {}
        
        return {
            'id': row['id'],
            'key_prefix': row['key_prefix'],
            'name': row['name'],
            'description': row['description'],
            'permissions': permissions,
            'rate_limit': row['rate_limit'],
            'enabled': bool(row['enabled']),
            'expires_at': row['expires_at'],
            'created_at': row['created_at'],
            'created_by': row['created_by'],
            'last_used_at': row['last_used_at'],
            'usage_count': row['usage_count'],
            'metadata': metadata
        }
    
    def revoke(self, name: str) -> bool:
        """Revoke (disable) an API key"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE api_keys SET enabled = 0 WHERE name = ?', (name,))
        conn.commit()
        
        changed = cursor.rowcount > 0
        conn.close()
        
        if changed:
            logger.info(f"✓ Revoked API key: {name}")
        
        return changed
    
    def delete(self, name: str) -> bool:
        """Permanently delete an API key"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get key_hash first
        cursor.execute('SELECT key_hash FROM api_keys WHERE name = ?', (name,))
        row = cursor.fetchone()
        
        if row:
            key_hash = row[0]
            # Delete usage logs
            cursor.execute('DELETE FROM api_key_usage WHERE key_hash = ?', (key_hash,))
            # Delete key
            cursor.execute('DELETE FROM api_keys WHERE name = ?', (name,))
            conn.commit()
            conn.close()
            
            logger.info(f"✓ Deleted API key: {name}")
            return True
        
        conn.close()
        return False
    
    def update(
        self,
        name: str,
        permissions: Optional[List[str]] = None,
        rate_limit: Optional[int] = None,
        description: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> bool:
        """Update API key properties"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if permissions is not None:
            updates.append('permissions = ?')
            params.append(json.dumps(permissions))
        
        if rate_limit is not None:
            updates.append('rate_limit = ?')
            params.append(rate_limit)
        
        if description is not None:
            updates.append('description = ?')
            params.append(description)
        
        if enabled is not None:
            updates.append('enabled = ?')
            params.append(1 if enabled else 0)
        
        if not updates:
            conn.close()
            return False
        
        params.append(name)
        query = f"UPDATE api_keys SET {', '.join(updates)} WHERE name = ?"
        
        cursor.execute(query, params)
        conn.commit()
        
        changed = cursor.rowcount > 0
        conn.close()
        
        if changed:
            logger.info(f"✓ Updated API key: {name}")
        
        return changed
    
    def get_usage_stats(self, name: str, days: int = 7) -> Dict[str, Any]:
        """Get usage statistics for an API key"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get key_hash
        cursor.execute('SELECT key_hash FROM api_keys WHERE name = ?', (name,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        key_hash = row[0]
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Total requests
        cursor.execute('''
            SELECT COUNT(*) as total,
                   AVG(response_time_ms) as avg_response_time,
                   MAX(response_time_ms) as max_response_time
            FROM api_key_usage
            WHERE key_hash = ? AND created_at >= ?
        ''', (key_hash, since))
        
        stats = cursor.fetchone()
        
        # Requests by endpoint
        cursor.execute('''
            SELECT endpoint, COUNT(*) as count
            FROM api_key_usage
            WHERE key_hash = ? AND created_at >= ?
            GROUP BY endpoint
            ORDER BY count DESC
            LIMIT 10
        ''', (key_hash, since))
        
        top_endpoints = [dict(row) for row in cursor.fetchall()]
        
        # Requests by status code
        cursor.execute('''
            SELECT status_code, COUNT(*) as count
            FROM api_key_usage
            WHERE key_hash = ? AND created_at >= ?
            GROUP BY status_code
        ''', (key_hash, since))
        
        status_codes = {row['status_code']: row['count'] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            'name': name,
            'period_days': days,
            'total_requests': stats['total'],
            'avg_response_time_ms': round(stats['avg_response_time'] or 0, 2),
            'max_response_time_ms': stats['max_response_time'] or 0,
            'top_endpoints': top_endpoints,
            'status_codes': status_codes
        }
