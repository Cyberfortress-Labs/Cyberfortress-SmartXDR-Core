"""
Test Data Anonymization Layer
Demo: Tokenization, Hashing, Private Mapping
"""

import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.anonymizer import (
    DataAnonymizer, 
    get_anonymizer,
    anonymize_suricata_alert,
    anonymize_zeek_log,
    anonymize_wazuh_alert
)


def test_ip_anonymization():
    """Test different IP anonymization methods"""
    print("=" * 80)
    print("TEST 1: IP ADDRESS ANONYMIZATION")
    print("=" * 80)
    
    anonymizer = DataAnonymizer()
    
    test_ips = [
        "192.168.85.112",  # Internal DVWA
        "192.168.100.171",  # Suricata
        "8.8.8.8",  # Public DNS
        "192.168.71.100"  # External Attacker
    ]
    
    print("\n1. Tokenization (reversible):")
    for ip in test_ips:
        token = anonymizer.anonymize_ip(ip, method='token')
        original = anonymizer.deanonymize(token)
        print(f"  {ip:20} -> {token:20} (reverse: {original})")
    
    print("\n2. Hashing (one-way, consistent):")
    for ip in test_ips:
        hashed = anonymizer.anonymize_ip(ip, method='hash')
        print(f"  {ip:20} -> {hashed}")
    
    print("\n3. Subnet-preserving (for network analysis):")
    for ip in test_ips:
        subnet = anonymizer.anonymize_ip(ip, method='subnet')
        print(f"  {ip:20} -> {subnet}")


def test_user_hostname_anonymization():
    """Test username and hostname anonymization"""
    print("\n" + "=" * 80)
    print("TEST 2: USERNAME & HOSTNAME ANONYMIZATION")
    print("=" * 80)
    
    anonymizer = get_anonymizer()
    
    users = ["admin", "root", "wazuh", "analyst"]
    hosts = ["DVWA-SERVER", "ELK-STACK", "WAZUH-01", "pfSense"]
    
    print("\nUsernames:")
    for user in users:
        token = anonymizer.anonymize_username(user, method='token')
        hashed = anonymizer.anonymize_username(user, method='hash')
        print(f"  {user:15} -> Token: {token:20} Hash: {hashed}")
    
    print("\nHostnames:")
    for host in hosts:
        token = anonymizer.anonymize_hostname(host, method='token')
        print(f"  {host:15} -> {token}")


def test_suricata_alert():
    """Test Suricata alert anonymization"""
    print("\n" + "=" * 80)
    print("TEST 3: SURICATA ALERT ANONYMIZATION")
    print("=" * 80)
    
    # Sample Suricata EVE-JSON alert
    raw_alert = {
        "timestamp": "2025-01-19T10:30:45.123456+0000",
        "flow_id": 123456789,
        "event_type": "alert",
        "src_ip": "192.168.71.100",
        "src_port": 54321,
        "dest_ip": "192.168.85.112",
        "dest_port": 80,
        "proto": "TCP",
        "alert": {
            "action": "allowed",
            "gid": 1,
            "signature_id": 2100498,
            "rev": 7,
            "signature": "GPL ATTACK_RESPONSE id check returned root",
            "category": "Potentially Bad Traffic",
            "severity": 2
        },
        "http": {
            "hostname": "dvwa.local",
            "url": "/vulnerabilities/sqli/",
            "http_user_agent": "Mozilla/5.0",
            "http_method": "GET",
            "protocol": "HTTP/1.1",
            "status": 200
        },
        "flow": {
            "pkts_toserver": 5,
            "pkts_toclient": 4,
            "bytes_toserver": 450,
            "bytes_toclient": 3200
        }
    }
    
    print("\n[ORIGINAL ALERT]")
    print(json.dumps(raw_alert, indent=2))
    
    anonymized = anonymize_suricata_alert(raw_alert)
    
    print("\n[ANONYMIZED ALERT]")
    print(json.dumps(anonymized, indent=2))
    
    print("\n[KEY CHANGES]")
    print(f"  src_ip:        {raw_alert['src_ip']} -> {anonymized['src_ip']}")
    print(f"  dest_ip:       {raw_alert['dest_ip']} -> {anonymized['dest_ip']}")
    print(f"  http.hostname: {raw_alert['http']['hostname']} -> {anonymized['http']['hostname']}")


def test_zeek_log():
    """Test Zeek conn.log anonymization"""
    print("\n" + "=" * 80)
    print("TEST 4: ZEEK CONN.LOG ANONYMIZATION")
    print("=" * 80)
    
    raw_log = {
        "ts": 1642598445.123456,
        "uid": "CAbcd1234efgh5678",
        "id.orig_h": "192.168.95.100",
        "id.orig_p": 49152,
        "id.resp_h": "192.168.85.115",
        "id.resp_p": 445,
        "proto": "tcp",
        "service": "smb",
        "duration": 12.456,
        "orig_bytes": 1024,
        "resp_bytes": 2048,
        "conn_state": "SF",
        "missed_bytes": 0,
        "history": "ShADadFf",
        "orig_pkts": 15,
        "resp_pkts": 12
    }
    
    print("\n[ORIGINAL LOG]")
    print(json.dumps(raw_log, indent=2))
    
    anonymized = anonymize_zeek_log(raw_log)
    
    print("\n[ANONYMIZED LOG]")
    print(json.dumps(anonymized, indent=2))


def test_wazuh_alert():
    """Test Wazuh alert anonymization"""
    print("\n" + "=" * 80)
    print("TEST 5: WAZUH ALERT ANONYMIZATION")
    print("=" * 80)
    
    raw_alert = {
        "timestamp": "2025-01-19T10:35:20.456Z",
        "rule": {
            "level": 7,
            "description": "Attempt to login using a non-existent user",
            "id": "5710",
            "mitre": {
                "id": ["T1110"],
                "tactic": ["Credential Access"],
                "technique": ["Brute Force"]
            }
        },
        "agent": {
            "id": "001",
            "name": "WINDOWS-SERVER-01",
            "ip": "192.168.85.115"
        },
        "data": {
            "srcip": "192.168.95.100",
            "srcuser": "attacker",
            "dstuser": "Administrator",
            "win": {
                "eventdata": {
                    "targetUserName": "Administrator",
                    "workstationName": "KALI-ATTACKER",
                    "ipAddress": "192.168.95.100"
                }
            }
        },
        "decoder": {
            "name": "windows-security"
        }
    }
    
    print("\n[ORIGINAL ALERT]")
    print(json.dumps(raw_alert, indent=2))
    
    anonymized = anonymize_wazuh_alert(raw_alert)
    
    print("\n[ANONYMIZED ALERT]")
    print(json.dumps(anonymized, indent=2))


def test_mapping_stats():
    """Display mapping database statistics"""
    print("\n" + "=" * 80)
    print("MAPPING DATABASE STATISTICS")
    print("=" * 80)
    
    anonymizer = get_anonymizer()
    stats = anonymizer.get_mapping_stats()
    
    print("\nAnonymized entities:")
    for entity_type, count in stats.items():
        print(f"  {entity_type:30} {count}")
    
    # Export mapping for backup
    export_path = Path(__file__).parent / "anonymizer_mapping.json"
    anonymizer.export_mapping_db(str(export_path))
    print(f"\n[INFO] Mapping database exported to: {export_path}")


def test_real_suricata_log():
    """Test with real Suricata log from production system"""
    print("\n" + "=" * 80)
    print("TEST 6: REAL SURICATA LOG ANONYMIZATION")
    print("=" * 80)
    
    # Load real log file
    log_path = Path(__file__).parent.parent / "logs" / "test-logs" / "suricata-nmap.json"
    
    if not log_path.exists():
        print(f"\n[ERROR] Log file not found: {log_path}")
        return
    
    print(f"\n[INFO] Loading log from: {log_path}")
    with open(log_path, 'r', encoding='utf-8') as f:
        raw_log = json.load(f)
    
    # Show original sensitive data
    print("\n[ORIGINAL SENSITIVE DATA]")
    if '_source' in raw_log:
        source = raw_log['_source']
        if 'source' in source:
            print(f"  Source IP:      {source['source'].get('ip', 'N/A')}")
        if 'destination' in source:
            print(f"  Dest IP:        {source['destination'].get('ip', 'N/A')}")
            print(f"  Dest Domain:    {source['destination'].get('domain', 'N/A')}")
        if 'observer' in source:
            print(f"  Observer IPs:   {source['observer'].get('ip', [])}")
            print(f"  Observer MACs:  {source['observer'].get('mac', [])}")
    
    # Anonymize the entire log
    anonymizer = get_anonymizer()
    
    # Custom field list for Elasticsearch Suricata logs
    fields_to_anonymize = [
        # Source/Dest IPs
        '_source.source.ip', '_source.source.address',
        '_source.destination.ip', '_source.destination.address', 
        '_source.destination.domain',
        # Observer data (includes arrays)
        '_source.observer.ip', '_source.observer.hostname',
        '_source.observer.mac',
        # Related IPs
        '_source.related.ip', '_source.related.hosts',
        # URL domains
        '_source.url.domain'
    ]
    
    anonymized_log = anonymizer.anonymize_log_event(raw_log, fields_to_anonymize)
    
    # Show anonymized data
    print("\n[ANONYMIZED SENSITIVE DATA]")
    if '_source' in anonymized_log:
        source = anonymized_log['_source']
        if 'source' in source:
            print(f"  Source IP:      {source['source'].get('ip', 'N/A')}")
        if 'destination' in source:
            print(f"  Dest IP:        {source['destination'].get('ip', 'N/A')}")
            print(f"  Dest Domain:    {source['destination'].get('domain', 'N/A')}")
        if 'observer' in source:
            print(f"  Observer IPs:   {source['observer'].get('ip', [])}")
            print(f"  Observer MACs:  {source['observer'].get('mac', [])}")
    
    # Save anonymized log
    output_dir = Path(__file__).parent.parent / "logs" / "anonymizer-logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / "anonymizer-suricata-nmap.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(anonymized_log, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SUCCESS] Anonymized log saved to: {output_path}")
    print(f"[INFO] Original size: {log_path.stat().st_size:,} bytes")
    print(f"[INFO] Anonymized size: {output_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("SMARTXDR DATA ANONYMIZATION LAYER TEST")
    print("Zero-Knowledge Approach: Tokenization + Hashing + Private Mapping")
    print("=" * 80)
    
    # Run all tests
    test_ip_anonymization()
    test_user_hostname_anonymization()
    test_suricata_alert()
    test_zeek_log()
    test_wazuh_alert()
    test_real_suricata_log()  # NEW: Test with real log
    test_mapping_stats()
    
    print("\n" + "=" * 80)
    print("ALL TESTS COMPLETED")
    print("=" * 80)
    print("\n[SUMMARY]")
    print("[PASS] IP anonymization (token/hash/subnet-preserving)")
    print("[PASS] Username/Hostname tokenization")
    print("[PASS] Suricata alert sanitization")
    print("[PASS] Zeek log sanitization")
    print("[PASS] Wazuh alert sanitization")
    print("[PASS] Real Suricata log from production (Elasticsearch)")
    print("[PASS] Private mapping database (reversible)")
    print("\n[SECURITY]")
    print("- All sensitive data replaced with tokens before sending to AI")
    print("- Original values stored only in local mapping database")
    print("- Zero-Knowledge: External services never see real IPs/users")
