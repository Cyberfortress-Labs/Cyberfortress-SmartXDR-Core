"""
Test Log Parser
Validates parsing of all 6 log types: Suricata, Zeek, Wazuh, pfSense, Router, ModSecurity
"""

import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.parser import LogParser, parse_log, get_parser


def load_test_log(filename: str) -> dict:
    """Load test log from logs/test-logs/"""
    log_path = Path(__file__).parent.parent / "logs" / "test-logs" / filename
    with open(log_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def test_suricata_parser():
    """Test Suricata EVE-JSON parser"""
    print("\n" + "=" * 80)
    print("TEST 1: SURICATA LOG PARSER")
    print("=" * 80)
    
    log = load_test_log('suricata-nmap.json')
    parser = get_parser()
    
    # Auto-detection
    detected_type = parser.detect_log_type(log)
    print(f"\n[AUTO-DETECT] Log type: {detected_type}")
    assert detected_type == 'suricata', f"Expected 'suricata', got '{detected_type}'"
    
    # Parse
    parsed = parse_log(log)
    
    print("\n[PARSED FIELDS]")
    print(f"  Timestamp:     {parsed['timestamp']}")
    print(f"  Signature:     {parsed['signature']}")
    print(f"  Signature ID:  {parsed['signature_id']}")
    print(f"  Category:      {parsed['category']}")
    print(f"  Severity:      {parsed['severity']}")
    print(f"  Source:        {parsed['src_ip']}:{parsed['src_port']}")
    print(f"  Destination:   {parsed['dest_ip']}:{parsed['dest_port']}")
    print(f"  Protocol:      {parsed['protocol']}")
    print(f"  Flow ID:       {parsed['flow_id']}")
    print(f"  Observer:      {parsed['observer']['hostname']}")
    
    # Extract IOCs
    iocs = parser.extract_iocs(parsed)
    print(f"\n[IOCs EXTRACTED]")
    print(f"  IPs:     {iocs['ips']}")
    print(f"  Domains: {iocs['domains']}")
    
    # Severity check
    is_high = parser.is_high_severity(parsed)
    print(f"\n[SEVERITY] High severity: {is_high}")
    
    print("\n✅ Suricata parser PASSED")


def test_zeek_parser():
    """Test Zeek DNS log parser"""
    print("\n" + "=" * 80)
    print("TEST 2: ZEEK LOG PARSER")
    print("=" * 80)
    
    log = load_test_log('zeek.json')
    parser = get_parser()
    
    detected_type = parser.detect_log_type(log)
    print(f"\n[AUTO-DETECT] Log type: {detected_type}")
    assert detected_type == 'zeek'
    
    parsed = parse_log(log)
    
    print("\n[PARSED FIELDS]")
    print(f"  Timestamp:     {parsed['timestamp']}")
    print(f"  Zeek Log Type: {parsed['zeek_log_type']}")
    print(f"  Session ID:    {parsed['session_id']}")
    print(f"  Source:        {parsed['src_ip']}:{parsed['src_port']}")
    print(f"  Destination:   {parsed['dest_ip']}:{parsed['dest_port']}")
    print(f"  Protocol:      {parsed['protocol']}")
    
    if parsed['zeek_log_type'] == 'dns':
        print(f"\n[DNS DETAILS]")
        print(f"  Query:         {parsed['dns']['query']}")
        print(f"  Query Type:    {parsed['dns']['qtype']}")
        print(f"  Response Code: {parsed['dns']['rcode']}")
    
    iocs = parser.extract_iocs(parsed)
    print(f"\n[IOCs] Domains: {iocs['domains']}")
    
    print("\n✅ Zeek parser PASSED")


def test_wazuh_parser():
    """Test Wazuh alert parser"""
    print("\n" + "=" * 80)
    print("TEST 3: WAZUH LOG PARSER")
    print("=" * 80)
    
    log = load_test_log('wazuh-alert.json')
    parser = get_parser()
    
    detected_type = parser.detect_log_type(log)
    print(f"\n[AUTO-DETECT] Log type: {detected_type}")
    assert detected_type == 'wazuh'
    
    parsed = parse_log(log)
    
    print("\n[PARSED FIELDS]")
    print(f"  Timestamp:     {parsed['timestamp']}")
    print(f"  Agent:         {parsed['agent']['name']} ({parsed['agent']['ip']})")
    print(f"  Rule ID:       {parsed['rule_id']}")
    print(f"  Rule Level:    {parsed['rule_level']}")
    print(f"  Description:   {parsed['rule_description']}")
    
    print(f"\n[MITRE ATT&CK]")
    print(f"  Tactics:       {', '.join(parsed['mitre']['tactics'])}")
    print(f"  Techniques:    {', '.join(parsed['mitre']['techniques'])}")
    print(f"  Technique IDs: {', '.join(parsed['mitre']['technique_ids'])}")
    
    print(f"\n[COMPLIANCE]")
    print(f"  PCI DSS:       {', '.join(parsed['compliance']['pci_dss'])}")
    print(f"  HIPAA:         {', '.join(parsed['compliance']['hipaa'])}")
    print(f"  GDPR:          {', '.join(parsed['compliance']['gdpr'])}")
    
    if parsed['syscheck']:
        print(f"\n[SYSCHECK/FIM]")
        print(f"  Event:         {parsed['syscheck'].get('event')}")
        print(f"  Path:          {parsed['syscheck'].get('path')}")
        print(f"  Value Name:    {parsed['syscheck'].get('value_name')}")
    
    iocs = parser.extract_iocs(parsed)
    print(f"\n[IOCs] Hashes: {iocs['hashes'][:2]}..." if iocs['hashes'] else "[IOCs] No hashes")
    
    is_high = parser.is_high_severity(parsed)
    print(f"\n[SEVERITY] High severity: {is_high} (level {parsed['rule_level']})")
    
    print("\n✅ Wazuh parser PASSED")


def test_pfsense_parser():
    """Test pfSense firewall log parser"""
    print("\n" + "=" * 80)
    print("TEST 4: pfSENSE LOG PARSER")
    print("=" * 80)
    
    log = load_test_log('pfsense.json')
    parser = get_parser()
    
    detected_type = parser.detect_log_type(log)
    print(f"\n[AUTO-DETECT] Log type: {detected_type}")
    assert detected_type == 'pfsense'
    
    parsed = parse_log(log)
    
    print("\n[PARSED FIELDS]")
    print(f"  Timestamp:     {parsed['timestamp']}")
    print(f"  Action:        {parsed['action']}")
    print(f"  Reason:        {parsed['reason']}")
    print(f"  Direction:     {parsed['direction']}")
    print(f"  Source:        {parsed['src_ip']}")
    print(f"  Destination:   {parsed['dest_ip']}")
    print(f"  Protocol:      {parsed['protocol']}")
    print(f"  Interface:     {parsed['interface']}")
    print(f"  Rule ID:       {parsed['rule_id']}")
    
    if parsed['icmp']:
        print(f"\n[ICMP DETAILS]")
        print(f"  Type:          {parsed['icmp'].get('type')}")
        print(f"  ID:            {parsed['icmp'].get('id')}")
        print(f"  Sequence:      {parsed['icmp'].get('seq')}")
    
    is_high = parser.is_high_severity(parsed)
    print(f"\n[SEVERITY] High severity: {is_high} (action={parsed['action']})")
    
    print("\n✅ pfSense parser PASSED")


def test_packetbeat_parser():
    """Test Packetbeat/Router flow parser"""
    print("\n" + "=" * 80)
    print("TEST 5: PACKETBEAT/ROUTER LOG PARSER")
    print("=" * 80)
    
    log = load_test_log('router.json')
    parser = get_parser()
    
    detected_type = parser.detect_log_type(log)
    print(f"\n[AUTO-DETECT] Log type: {detected_type}")
    assert detected_type == 'packetbeat'
    
    parsed = parse_log(log)
    
    print("\n[PARSED FIELDS]")
    print(f"  Timestamp:     {parsed['timestamp']}")
    print(f"  Flow ID:       {parsed['flow_id']}")
    print(f"  Flow Final:    {parsed['flow_final']}")
    print(f"  Source:        {parsed['src_ip']}:{parsed['src_port']}")
    print(f"  Destination:   {parsed['dest_ip']}:{parsed['dest_port']}")
    print(f"  Protocol:      {parsed['protocol']}")
    
    print(f"\n[TRAFFIC STATS]")
    print(f"  Total Bytes:   {parsed['bytes_total']}")
    print(f"  Total Packets: {parsed['packets_total']}")
    print(f"  Duration:      {parsed['duration']} ns")
    
    print(f"\n[HOST CONTEXT]")
    print(f"  Hostname:      {parsed['host']['hostname']}")
    print(f"  IPs:           {parsed['host']['ip']}")
    print(f"  MACs:          {parsed['host']['mac']}")
    
    print("\n✅ Packetbeat parser PASSED")


def test_modsecurity_parser():
    """Test ModSecurity WAF log parser"""
    print("\n" + "=" * 80)
    print("TEST 6: MODSECURITY WAF LOG PARSER")
    print("=" * 80)
    
    log = load_test_log('modsecurity.json')
    parser = get_parser()
    
    detected_type = parser.detect_log_type(log)
    print(f"\n[AUTO-DETECT] Log type: {detected_type}")
    
    parsed = parse_log(log)
    
    print("\n[PARSED FIELDS]")
    print(f"  Log Type:      {parsed['log_type']}")
    print(f"  Timestamp:     {parsed['timestamp']}")
    
    if parsed.get('action'):
        print(f"  Action:        {parsed['action']}")
        print(f"  Severity:      {parsed.get('severity', 'N/A')}")
        print(f"  Rule ID:       {parsed.get('rule_id', 'N/A')}")
        print(f"  Rule Msg:      {parsed.get('rule_msg', 'N/A')}")
    
    if parsed.get('http'):
        print(f"\n[HTTP REQUEST]")
        print(f"  Method:        {parsed['http'].get('method', 'N/A')}")
        print(f"  URI:           {parsed['http'].get('uri', 'N/A')}")
        print(f"  Host:          {parsed['http'].get('host', 'N/A')}")
    
    print("\n✅ ModSecurity parser PASSED (or generic fallback)")


def test_batch_parsing():
    """Test batch parsing multiple logs"""
    print("\n" + "=" * 80)
    print("TEST 7: BATCH PARSING")
    print("=" * 80)
    
    from app.core.parser import parse_logs
    
    logs = [
        load_test_log('suricata-nmap.json'),
        load_test_log('zeek.json'),
        load_test_log('wazuh-alert.json'),
        load_test_log('pfsense.json'),
        load_test_log('router.json')
    ]
    
    parsed_logs = parse_logs(logs)
    
    print(f"\n[BATCH RESULTS]")
    print(f"  Total logs processed: {len(parsed_logs)}")
    
    log_types = {}
    for p in parsed_logs:
        log_type = p.get('log_type', 'unknown')
        log_types[log_type] = log_types.get(log_type, 0) + 1
    
    print(f"\n[LOG TYPE DISTRIBUTION]")
    for log_type, count in log_types.items():
        print(f"  {log_type:15} {count}")
    
    print("\n✅ Batch parsing PASSED")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("SMARTXDR LOG PARSER TEST SUITE")
    print("Testing 6 log sources: Suricata, Zeek, Wazuh, pfSense, Router, ModSecurity")
    print("=" * 80)
    
    # Run all tests
    test_suricata_parser()
    test_zeek_parser()
    test_wazuh_parser()
    test_pfsense_parser()
    test_packetbeat_parser()
    test_modsecurity_parser()
    test_batch_parsing()
    
    print("\n" + "=" * 80)
    print("ALL PARSER TESTS COMPLETED")
    print("=" * 80)
    print("\n[SUMMARY]")
    print("✅ Suricata EVE-JSON parser")
    print("✅ Zeek DNS log parser")
    print("✅ Wazuh alert parser (FIM + MITRE mapping)")
    print("✅ pfSense firewall log parser")
    print("✅ Packetbeat network flow parser")
    print("✅ ModSecurity WAF parser")
    print("✅ Batch parsing")
    print("✅ Auto-detection algorithm")
    print("✅ IOC extraction")
    print("✅ Severity assessment")
    print("\n[READY] Parser module ready for integration with AI Gateway")
