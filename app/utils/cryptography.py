"""
Cryptography utilities for SmartXDR Core.

This module provides secure hashing and verification functions using Argon2id,
which is more secure than SHA-256 for password/API key hashing.

Argon2id is the recommended algorithm for password hashing by OWASP.
It provides resistance against:
- GPU cracking attacks
- Side-channel attacks
- Time-memory trade-off attacks
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
import logging

logger = logging.getLogger(__name__)

# Initialize Argon2 password hasher with secure parameters
# time_cost: Number of iterations (default: 2)
# memory_cost: Memory usage in kibibytes (default: 102400 = 100 MiB)
# parallelism: Number of parallel threads (default: 8)
# hash_len: Length of the hash in bytes (default: 16)
# salt_len: Length of the random salt in bytes (default: 16)
ph = PasswordHasher(
    time_cost=3,        # Increased iterations for better security
    memory_cost=65536,  # 64 MiB - balanced for server use
    parallelism=4,      # 4 threads - good for multi-core servers
    hash_len=32,        # 32 bytes = 256 bits output
    salt_len=16         # 16 bytes = 128 bits salt
)


def hash_password(password: str) -> str:
    """
    Hash a password or API key using Argon2id.
    
    Args:
        password: The plaintext password or API key to hash
        
    Returns:
        The Argon2id hash string in PHC format:
        $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
        
    Example:
        >>> hashed = hash_password("sxdr_abc123...")
        >>> print(hashed)
        $argon2id$v=19$m=65536,t=3,p=4$randomsalt$randomhash
    """
    try:
        hashed = ph.hash(password)
        logger.debug(f"Successfully hashed password (length: {len(password)})")
        return hashed
    except Exception as e:
        logger.error(f"Failed to hash password: {e}")
        raise


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password or API key against its Argon2id hash.
    
    Args:
        password: The plaintext password or API key to verify
        hashed: The Argon2id hash to verify against
        
    Returns:
        True if the password matches the hash, False otherwise
        
    Example:
        >>> hashed = hash_password("sxdr_abc123...")
        >>> verify_password("sxdr_abc123...", hashed)
        True
        >>> verify_password("wrong_key", hashed)
        False
    """
    try:
        ph.verify(hashed, password)
        logger.debug("Password verification successful")
        
        # Check if the hash needs rehashing (parameters changed)
        if ph.check_needs_rehash(hashed):
            logger.info("Hash parameters outdated, consider rehashing")
            
        return True
    except VerifyMismatchError:
        logger.debug("Password verification failed: mismatch")
        return False
    except (VerificationError, InvalidHash) as e:
        logger.warning(f"Password verification error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during password verification: {e}")
        return False


def needs_rehash(hashed: str) -> bool:
    """
    Check if a hash needs to be rehashed with updated parameters.
    
    This is useful when you update the Argon2 parameters (time_cost, memory_cost, etc.)
    and want to migrate old hashes to the new parameters.
    
    Args:
        hashed: The Argon2id hash to check
        
    Returns:
        True if the hash should be regenerated with new parameters
        
    Example:
        >>> if needs_rehash(stored_hash):
        >>>     new_hash = hash_password(plaintext_key)
        >>>     update_database(new_hash)
    """
    try:
        return ph.check_needs_rehash(hashed)
    except Exception as e:
        logger.warning(f"Failed to check rehash status: {e}")
        return False


# Backward compatibility wrapper for migration from SHA-256
def is_argon2_hash(hashed: str) -> bool:
    """
    Check if a hash string is in Argon2 format.
    
    This helps distinguish between old SHA-256 hashes and new Argon2 hashes
    during migration.
    
    Args:
        hashed: The hash string to check
        
    Returns:
        True if the hash is in Argon2 format, False otherwise
        
    Example:
        >>> is_argon2_hash("$argon2id$v=19$...")
        True
        >>> is_argon2_hash("a1b2c3d4e5f6...")  # SHA-256 hex
        False
    """
    return hashed.startswith('$argon2')


def hash_api_key(api_key: str) -> str:
    """
    Convenience wrapper for hashing API keys.
    Alias for hash_password() with clearer naming.
    
    Args:
        api_key: The plaintext API key to hash
        
    Returns:
        The Argon2id hash string
    """
    return hash_password(api_key)


def verify_api_key(api_key: str, hashed: str) -> bool:
    """
    Convenience wrapper for verifying API keys.
    Alias for verify_password() with clearer naming.
    
    Args:
        api_key: The plaintext API key to verify
        hashed: The Argon2id hash to verify against
        
    Returns:
        True if the API key matches the hash, False otherwise
    """
    return verify_password(api_key, hashed)
