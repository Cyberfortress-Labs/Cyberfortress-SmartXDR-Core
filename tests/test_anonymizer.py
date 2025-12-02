"""
Comprehensive tests for SecureLogAnonymizer
Tests HMAC consistency, encryption, IPv4/IPv6, email, URL, MAC, and JSON anonymization
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest

import json
import secrets
from pathlib import Path
from app.core.anonymizer import (
    SecureLogAnonymizer,
    DataAnonymizer,  # Test backward compatibility
    KeyManager,
    get_anonymizer,
    anonymize_log,
    get_key_manager
)


def dump_mappings(anon: SecureLogAnonymizer, limit_per_cat: int = 5):
    """Helper to print a brief summary of mapping DB and stats (not full dump)."""
    stats = anon.get_stats()
    print("=== MAPPING SUMMARY ===")
    print(f"Total anonymized: {stats.get('total_anonymized')}")
    print("Counts by category:")
    for k, v in stats.get('mapping_counts', {}).items():
        print(f"  - {k}: {v}")
    print("Sample mappings (up to {} each):".format(limit_per_cat))
    for cat, mapping in anon._mapping_db.items():
        if not mapping:
            continue
        print(f"  [{cat}] ({len(mapping)} items) -> sample:")
        i = 0
        for orig, anonv in mapping.items():
            print(f"    {orig!r} => {anonv!r}")
            i += 1
            if i >= limit_per_cat:
                break
    print("=======================\n")


class TestKeyManager:
    """Test KeyManager for secure key handling"""
    
    def test_generate_key_for_env(self):
        """Test key generation for environment variable"""
        key = KeyManager.generate_key_for_env()
        print("Generated env key (truncated):", key[:16] + "...")
        assert isinstance(key, str)
        assert len(key) == 64  # 32 bytes = 64 hex chars
        assert all(c in '0123456789abcdef' for c in key)
    
    def test_get_key_from_env(self, monkeypatch):
        """Test retrieving key from environment variable"""
        test_key = KeyManager.generate_key_for_env()
        monkeypatch.setenv('ANONYMIZER_ENCRYPTION_KEY', test_key)
        
        km = KeyManager()
        key = km.get_key(auto_generate=False)
        
        print("KeyManager returned key (hex truncated):", key.hex()[:16] + "...")
        assert key is not None
        assert len(key) == 32
        assert key.hex() == test_key
    
    def test_auto_generate_key(self, tmp_path, monkeypatch):
        """Test auto-generation and saving of key"""
        # Use temporary directory
        key_file = tmp_path / "test.key"
        monkeypatch.delenv('ANONYMIZER_ENCRYPTION_KEY', raising=False)
        
        km = KeyManager(key_file_path=key_file)
        key1 = km.get_key(auto_generate=True)
        
        print("Auto-generated key saved to:", str(key_file))
        assert key1 is not None
        assert len(key1) == 32
        assert key_file.exists()
        
        # Second call should return cached key
        key2 = km.get_key(auto_generate=True)
        assert key1 == key2
    
    def test_key_rotation(self, tmp_path, monkeypatch):
        """Test key rotation"""
        key_file = tmp_path / "test.key"
        monkeypatch.delenv('ANONYMIZER_ENCRYPTION_KEY', raising=False)
        
        km = KeyManager(key_file_path=key_file)
        key1 = km.get_key(auto_generate=True)
        
        # Rotate key
        key2 = km.rotate_key()
        
        print("Rotated key: before (trunc) ->", key1.hex()[:8] + "...", "after (trunc) ->", key2.hex()[:8] + "...")
        assert key1 != key2
        assert len(key2) == 32


class TestHMACConsistency:
    """Test HMAC-based consistent hashing"""
    
    def test_hmac_consistent_hash(self):
        """Test that same input produces same hash"""
        key = secrets.token_bytes(32)
        anon1 = SecureLogAnonymizer(hmac_key=key)
        anon2 = SecureLogAnonymizer(hmac_key=key)
        
        # Same input should produce same hash
        ip1 = anon1.anonymize_ip("192.168.1.100")
        ip2 = anon2.anonymize_ip("192.168.1.100")
        
        print("HMAC consistency test -> ip1:", ip1, "ip2:", ip2)
        assert ip1 == ip2
    
    def test_different_keys_different_hashes(self):
        """Test that different keys produce different hashes"""
        anon1 = SecureLogAnonymizer(hmac_key=secrets.token_bytes(32))
        anon2 = SecureLogAnonymizer(hmac_key=secrets.token_bytes(32))
        
        ip1 = anon1.anonymize_ip("192.168.1.100")
        ip2 = anon2.anonymize_ip("192.168.1.100")
        
        print("Different-keys test -> ip1:", ip1, "ip2:", ip2)
        assert ip1 != ip2
    
    def test_singleton_consistency(self):
        """Test singleton anonymizer maintains consistency"""
        anon1 = get_anonymizer()
        
        ip1 = anon1.anonymize_ip("10.0.0.1")
        ip2 = anon1.anonymize_ip("10.0.0.1")
        
        print("Singleton outputs:", ip1, ip2)
        assert ip1 == ip2


class TestIPv4Anonymization:
    """Test IPv4 address anonymization"""
    
    def test_ipv4_subnet_preservation(self):
        """Test IPv4 subnet preservation (/16)"""
        anon = SecureLogAnonymizer(preserve_subnet_prefix=16)
        
        ip1 = anon.anonymize_ip("192.168.1.100")
        ip2 = anon.anonymize_ip("192.168.2.100")
        
        print("IPv4 preserve example ->", ip1, ip2)
        # First two octets should match (same subnet)
        assert ip1.split('.')[0] == ip2.split('.')[0]
        assert ip1.split('.')[1] == ip2.split('.')[1]
    
    def test_ipv4_different_subnet_different_hash(self):
        """Test different subnets produce different hashes"""
        anon = SecureLogAnonymizer(preserve_subnet_prefix=16)
        
        ip1 = anon.anonymize_ip("192.168.1.100")
        ip2 = anon.anonymize_ip("192.167.1.100")  # Different /16
        
        print("IPv4 different-subnet ->", ip1, ip2)
        # At least last two octets should differ
        octets1 = ip1.split('.')
        octets2 = ip2.split('.')
        
        assert not (octets1[2] == octets2[2] and octets1[3] == octets2[3])
    
    def test_reserved_ipv4_not_anonymized(self):
        """Test reserved IPv4 addresses are not anonymized"""
        anon = SecureLogAnonymizer()
        
        print("Reserved checks:", anon.anonymize_ip("127.0.0.1"), anon.anonymize_ip("0.0.0.0"))
        assert anon.anonymize_ip("127.0.0.1") == "127.0.0.1"
        assert anon.anonymize_ip("0.0.0.0") == "0.0.0.0"
        assert anon.anonymize_ip("255.255.255.255") == "255.255.255.255"
    
    def test_invalid_ipv4_returned_as_is(self):
        """Test invalid IPv4 addresses are returned unchanged"""
        anon = SecureLogAnonymizer()
        
        print("Invalid IPs:", anon.anonymize_ip("not-an-ip"), anon.anonymize_ip("999.999.999.999"))
        assert anon.anonymize_ip("not-an-ip") == "not-an-ip"
        assert anon.anonymize_ip("999.999.999.999") == "999.999.999.999"


class TestIPv6Anonymization:
    """Test IPv6 address anonymization"""
    
    def test_ipv6_anonymization(self):
        """Test IPv6 address anonymization"""
        anon = SecureLogAnonymizer(preserve_subnet_prefix_v6=48)
        
        ip = anon.anonymize_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334")
        
        print("IPv6 anon example:", ip)
        assert ip != "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        assert ':' in ip  # Should still be IPv6 format
    
    def test_reserved_ipv6_not_anonymized(self):
        """Test reserved IPv6 addresses are not anonymized"""
        anon = SecureLogAnonymizer()
        
        print("Reserved IPv6 check:", anon.anonymize_ip("::1"), anon.anonymize_ip("::"))
        assert anon.anonymize_ip("::1") == "::1"  # loopback
        assert anon.anonymize_ip("::") == "::"    # all zeros


class TestEmailAnonymization:
    """Test email address anonymization"""
    
    def test_email_anonymization(self):
        """Test email anonymization preserves structure"""
        anon = SecureLogAnonymizer()
        
        anon_email = anon.anonymize_email("user@example.com")
        
        print("Email anon:", anon_email)
        # Should contain @
        assert '@' in anon_email
        # Should have user-xxx format
        assert anon_email.startswith("user-")
        # Should preserve TLD
        assert anon_email.endswith(".com")
    
    def test_email_consistency(self):
        """Test same email produces same anonymized result"""
        key = secrets.token_bytes(32)
        anon1 = SecureLogAnonymizer(hmac_key=key)
        anon2 = SecureLogAnonymizer(hmac_key=key)
        
        email = "alice@company.com"
        anon_email1 = anon1.anonymize_email(email)
        anon_email2 = anon2.anonymize_email(email)
        
        print("Email consistency:", anon_email1, anon_email2)
        assert anon_email1 == anon_email2
    
    def test_invalid_email_returned_as_is(self):
        """Test invalid email is returned unchanged"""
        anon = SecureLogAnonymizer()
        
        assert anon.anonymize_email("not-an-email") == "not-an-email"


class TestMACAnonymization:
    """Test MAC address anonymization"""
    
    def test_mac_oui_preservation(self):
        """Test MAC OUI (manufacturer prefix) is preserved"""
        anon = SecureLogAnonymizer()
        
        mac = anon.anonymize_mac("AA:BB:CC:DD:EE:FF")
        parts = mac.split(':')
        
        print("MAC anon:", mac)
        # OUI preserved (first 3 octets)
        assert parts[0] == "aa"
        assert parts[1] == "bb"
        assert parts[2] == "cc"
    
    def test_mac_normalization(self):
        """Test MAC address normalization"""
        anon = SecureLogAnonymizer()
        
        # Different formats should normalize
        mac1 = anon.anonymize_mac("AA-BB-CC-DD-EE-FF")
        mac2 = anon.anonymize_mac("aabbccddeeff")
        mac3 = anon.anonymize_mac("AABB.CCDD.EEFF")
        
        print("MAC variants ->", mac1, mac2, mac3)
        # All should normalize to same key internally
        assert anon.anonymize_mac("AA:BB:CC:DD:EE:FF") == mac1


class TestURLAnonymization:
    """Test URL anonymization"""
    
    def test_url_anonymization(self):
        """Test URL is anonymized while preserving structure"""
        anon = SecureLogAnonymizer()
        
        url = "https://user@example.com:8080/api/users/123?id=456&email=test@test.com"
        anon_url = anon.anonymize_url(url)
        
        print("URL anon:", anon_url)
        # Should still be a URL
        assert "://" in anon_url
        # Hostname should be anonymized
        assert "example.com" not in anon_url
    
    def test_url_consistency(self):
        """Test same URL produces same anonymized result"""
        key = secrets.token_bytes(32)
        anon1 = SecureLogAnonymizer(hmac_key=key)
        anon2 = SecureLogAnonymizer(hmac_key=key)
        
        url = "https://api.github.com/users/alice"
        anon_url1 = anon1.anonymize_url(url)
        anon_url2 = anon2.anonymize_url(url)
        
        print("URL consistency:", anon_url1, anon_url2)
        assert anon_url1 == anon_url2


class TestDomainAnonymization:
    """Test domain name anonymization"""
    
    def test_domain_tld_preservation(self):
        """Test TLD is preserved"""
        anon = SecureLogAnonymizer()
        
        dom1 = anon.anonymize_domain("example.com")
        dom2 = anon.anonymize_domain("test.org")
        
        print("Domains anon:", dom1, dom2)
        # TLDs preserved
        assert dom1.endswith(".com")
        assert dom2.endswith(".org")
    
    def test_domain_consistency(self):
        """Test same domain produces same result"""
        key = secrets.token_bytes(32)
        anon1 = SecureLogAnonymizer(hmac_key=key)
        anon2 = SecureLogAnonymizer(hmac_key=key)
        
        domain = "api.example.com"
        dom1 = anon1.anonymize_domain(domain)
        dom2 = anon2.anonymize_domain(domain)
        
        print("Domain consistency:", dom1, dom2)
        assert dom1 == dom2


class TestTextAnonymization:
    """Test text anonymization with multiple types"""
    
    def test_anonymize_text_with_ips(self):
        """Test IP anonymization in text"""
        anon = SecureLogAnonymizer()
        
        text = "Connection from 192.168.1.100 to 10.0.0.1"
        anon_text = anon.anonymize_text(text, anonymize_ips=True)
        
        print("Text anon (IPs):", anon_text)
        assert "192.168.1.100" not in anon_text
        assert "10.0.0.1" not in anon_text
    
    def test_anonymize_text_with_emails(self):
        """Test email anonymization in text"""
        anon = SecureLogAnonymizer()
        
        text = "Contact admin@example.com or support@test.org"
        anon_text = anon.anonymize_text(text, anonymize_emails=True)
        
        print("Text anon (emails):", anon_text)
        assert "admin@example.com" not in anon_text
        assert "support@test.org" not in anon_text
    
    def test_anonymize_text_selective(self):
        """Test selective anonymization"""
        anon = SecureLogAnonymizer()
        
        text = "IP: 192.168.1.1, Email: user@test.com, MAC: AA:BB:CC:DD:EE:FF"
        
        # Only anonymize IPs
        anon_text = anon.anonymize_text(
            text,
            anonymize_ips=True,
            anonymize_emails=False,
            anonymize_macs=False
        )
        
        print("Text selective anon:", anon_text)
        assert "192.168.1.1" not in anon_text
        assert "user@test.com" in anon_text
        assert "AA:BB:CC:DD:EE:FF" in anon_text or "aa:bb:cc:dd:ee:ff" in anon_text


class TestJSONAnonymization:
    """Test JSON structure anonymization"""
    
    def test_anonymize_json_dict(self):
        """Test JSON dict anonymization"""
        anon = SecureLogAnonymizer()
        
        data = {
            "source_ip": "192.168.1.1",
            "dest_ip": "10.0.0.1",
            "user": "admin",
            "email": "admin@example.com"
        }
        
        anon_data = anon.anonymize_json(data)
        
        print("Anon JSON dict:", anon_data)
        dump_mappings(anon)
        # Values should be anonymized
        assert anon_data["source_ip"] != "192.168.1.1"
        assert anon_data["dest_ip"] != "10.0.0.1"
        assert anon_data["user"] != "admin"
        assert anon_data["email"] != "admin@example.com"
    
    def test_anonymize_json_nested(self):
        """Test nested JSON anonymization"""
        anon = SecureLogAnonymizer()
        
        data = {
            "user": {
                "username": "alice",
                "email": "alice@test.com"
            },
            "source_ip": "192.168.1.100"
        }
        
        anon_data = anon.anonymize_json(data)
        
        print("Anon nested JSON:", anon_data)
        dump_mappings(anon)
        assert anon_data["user"]["username"] != "alice"
        assert anon_data["user"]["email"] != "alice@test.com"
        assert anon_data["source_ip"] != "192.168.1.100"
    
    def test_anonymize_json_list(self):
        """Test JSON list anonymization"""
        anon = SecureLogAnonymizer()
        
        data = {
            "ips": ["192.168.1.1", "10.0.0.1"],
            "emails": ["user1@test.com", "user2@test.com"]
        }
        
        anon_data = anon.anonymize_json(data)
        
        print("Anon JSON list:", anon_data)
        dump_mappings(anon)
        assert "192.168.1.1" not in anon_data["ips"]
        assert "10.0.0.1" not in anon_data["ips"]


class TestExportImport:
    """Test mapping database export/import"""
    
    def test_export_unencrypted(self):
        """Test unencrypted export"""
        anon = SecureLogAnonymizer()
        anon.anonymize_ip("192.168.1.1")
        anon.anonymize_email("user@test.com")
        
        data = anon.export_mapping_db(use_key_manager=False)
        
        print("Export (unencrypted) length:", len(data))
        assert isinstance(data, bytes)
        # Should be JSON
        json_data = json.loads(data.decode('utf-8'))
        print("Export JSON keys:", list(json_data.keys()))
        assert "mappings" in json_data
        assert "ip" in json_data["mappings"]
    
    def test_export_import_roundtrip(self):
        """Test export and import roundtrip"""
        key = secrets.token_bytes(32)
        anon1 = SecureLogAnonymizer(hmac_key=key)
        
        # Create some mappings
        ip1 = anon1.anonymize_ip("192.168.1.1")
        email1 = anon1.anonymize_email("user@test.com")
        print("anon1 sample ->", ip1, email1)
        
        # Export with password
        exported = anon1.export_mapping_db(password="test123", use_key_manager=False)
        print("Exported encrypted length:", len(exported), "version byte:", exported[0])
        
        # Create new instance and import
        anon2 = SecureLogAnonymizer(hmac_key=key)
        anon2.import_mapping_db(exported, password="test123")
        
        # Mappings should be restored
        ip2 = anon2.anonymize_ip("192.168.1.1")
        email2 = anon2.anonymize_email("user@test.com")
        print("anon2 sample after import ->", ip2, email2)
        
        assert ip1 == ip2
        assert email1 == email2
    
    def test_import_wrong_password_fails(self):
        """Test import with wrong password fails"""
        anon1 = SecureLogAnonymizer()
        anon1.anonymize_ip("192.168.1.1")
        
        exported = anon1.export_mapping_db(password="correct123", use_key_manager=False)
        
        anon2 = SecureLogAnonymizer()
        
        with pytest.raises(ValueError) as excinfo:
            anon2.import_mapping_db(exported, password="wrong123")
        # print the exception message for debug visibility
        print("Import failed as expected:", str(excinfo.value))
        assert "wrong password" in str(excinfo.value).lower()


class TestReverseMapping:
    """Test reverse mapping functionality"""
    
    def test_get_reverse_mapping(self):
        """Test retrieving original from anonymized value"""
        anon = SecureLogAnonymizer()
        
        original_ip = "192.168.1.1"
        anon_ip = anon.anonymize_ip(original_ip)
        print("Reverse mapping lookup for:", anon_ip)
        
        result = anon.get_reverse_mapping(anon_ip)
        print("Reverse mapping result:", result)
        
        assert result is not None
        assert result[0] == original_ip
        assert result[1] == "ip"
    
    def test_reverse_mapping_not_found(self):
        """Test reverse mapping for unknown value"""
        anon = SecureLogAnonymizer()
        
        result = anon.get_reverse_mapping("unknown_value")
        print("Reverse mapping unknown ->", result)
        
        assert result is None


class TestBackwardCompatibility:
    """Test backward compatibility"""
    
    def test_data_anonymizer_alias(self):
        """Test DataAnonymizer alias works"""
        # Should be able to import and use old class name
        anon = DataAnonymizer()
        
        ip = anon.anonymize_ip("192.168.1.1")
        print("DataAnonymizer alias ->", ip)
        assert ip != "192.168.1.1"
    
    def test_anonymize_log_function(self):
        """Test convenience anonymize_log function"""
        data = {"source_ip": "192.168.1.1", "message": "test"}
        
        anon_data = anonymize_log(data)
        print("anonymize_log output:", anon_data)
        assert anon_data["source_ip"] != "192.168.1.1"


class TestStatistics:
    """Test statistics tracking"""
    
    def test_get_stats(self):
        """Test statistics retrieval"""
        anon = SecureLogAnonymizer()
        
        anon.anonymize_ip("192.168.1.1")
        anon.anonymize_email("user@test.com")
        anon.anonymize_ip("10.0.0.1")
        
        stats = anon.get_stats()
        print("Stats:", stats)
        
        assert stats["total_anonymized"] == 3
        assert stats["by_type"]["ip"] == 2
        assert stats["by_type"]["email"] == 1
    
    def test_clear_mappings(self):
        """Test clearing mappings"""
        anon = SecureLogAnonymizer()
        
        anon.anonymize_ip("192.168.1.1")
        anon.anonymize_email("user@test.com")
        
        # Clear IP mappings only
        anon.clear_mappings(["ip"])
        
        stats = anon.get_stats()
        print("Stats after clear:", stats)
        assert stats["by_type"]["ip"] == 0
        assert stats["by_type"]["email"] == 1


if __name__ == "__main__":
    # Run with -s to see prints: pytest -s <this_file>
    pytest.main([__file__, "-q"])
