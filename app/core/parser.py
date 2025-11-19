"""
Log Parser for SmartXDR
Parses logs from multiple sources: Suricata, Zeek, Wazuh, pfSense, Router (Packetbeat), ModSecurity
Standardizes heterogeneous log formats into a unified structure for AI analysis
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import re


class LogParser:
    """
    Universal log parser supporting multiple security data sources
    Extracts key fields and normalizes to a common schema
    """
    
    def __init__(self):
        self.supported_sources = [
            'suricata', 'zeek', 'wazuh', 'pfsense', 
            'packetbeat', 'modsecurity', 'elasticsearch'
        ]
    
    # ==================== AUTO-DETECTION ====================
    
    def detect_log_type(self, log: Dict[str, Any]) -> str:
        """
        Auto-detect log source type from structure
        
        Args:
            log: Raw log JSON
            
        Returns:
            Log source type (suricata, zeek, wazuh, etc.)
        """
        # Check Elasticsearch _source wrapper
        source = log.get('_source', log)
        
        # Suricata: Has suricata.eve field
        if 'suricata' in source:
            return 'suricata'
        
        # Zeek: Has zeek.session_id or zeek.dns
        if 'zeek' in source:
            return 'zeek'
        
        # Wazuh: Has syscheck or rule.mitre
        if 'syscheck' in source or ('rule' in source and 'mitre' in source.get('rule', {})):
            return 'wazuh'
        
        # pfSense: Has pfsense field and observer.vendor = "netgate"
        if 'pfsense' in source or (source.get('observer', {}).get('vendor') == 'netgate'):
            return 'pfsense'
        
        # Packetbeat/Router: Has network_traffic.flow
        if 'network_traffic' in source:
            return 'packetbeat'
        
        # ModSecurity: Has modsecurity field or WAF-related data
        if 'modsecurity' in source or 'waf' in source:
            return 'modsecurity'
        
        # Check data_stream.dataset for Elastic modules
        dataset = source.get('data_stream', {}).get('dataset', '')
        if 'suricata' in dataset:
            return 'suricata'
        elif 'zeek' in dataset:
            return 'zeek'
        elif 'pfsense' in dataset:
            return 'pfsense'
        
        return 'unknown'
    
    # ==================== UNIVERSAL PARSER ====================
    
    def parse(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Universal parser - auto-detects type and routes to specific parser
        
        Args:
            log: Raw log from any source
            
        Returns:
            Parsed and normalized log structure
        """
        log_type = self.detect_log_type(log)
        
        parsers = {
            'suricata': self.parse_suricata,
            'zeek': self.parse_zeek,
            'wazuh': self.parse_wazuh,
            'pfsense': self.parse_pfsense,
            'packetbeat': self.parse_packetbeat,
            'modsecurity': self.parse_modsecurity
        }
        
        parser_func = parsers.get(log_type, self.parse_generic)
        parsed = parser_func(log)
        
        # Add metadata
        parsed['_parser_metadata'] = {
            'detected_type': log_type,
            'parsed_at': datetime.utcnow().isoformat(),
            'original_index': log.get('_index', 'unknown')
        }
        
        return parsed
    
    # ==================== SURICATA PARSER ====================
    
    def parse_suricata(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Suricata EVE-JSON alert
        Example: ET SCAN Nmap Scripting Engine detection
        """
        source = log.get('_source', log)
        suricata = source.get('suricata', {}).get('eve', {})
        
        return {
            'log_type': 'suricata',
            'timestamp': source.get('@timestamp'),
            'event_type': suricata.get('event_type', 'alert'),
            
            # Network 5-tuple
            'src_ip': source.get('source', {}).get('ip'),
            'src_port': source.get('source', {}).get('port'),
            'dest_ip': source.get('destination', {}).get('ip'),
            'dest_port': source.get('destination', {}).get('port'),
            'protocol': source.get('network', {}).get('transport'),
            
            # Alert details
            'signature': source.get('rule', {}).get('name') or suricata.get('alert', {}).get('signature'),
            'signature_id': source.get('rule', {}).get('id') or suricata.get('alert', {}).get('signature_id'),
            'category': source.get('rule', {}).get('category') or suricata.get('alert', {}).get('category'),
            'severity': source.get('event', {}).get('severity', 0),
            
            # Context
            'flow_id': suricata.get('flow_id'),
            'community_id': source.get('network', {}).get('community_id'),
            
            # Protocol-specific
            'http': source.get('http', {}),
            'dns': source.get('dns', {}),
            'tls': source.get('tls', {}),
            
            # Enrichment
            'observer': {
                'hostname': source.get('observer', {}).get('hostname'),
                'ip': source.get('observer', {}).get('ip', []),
                'interface': suricata.get('in_iface')
            },
            
            # Traffic stats
            'bytes_total': source.get('network', {}).get('bytes'),
            'packets_total': source.get('network', {}).get('packets'),
            
            # Raw for reference
            '_raw': {
                'message': source.get('message'),
                'full_alert': suricata.get('alert', {})
            }
        }
    
    # ==================== ZEEK PARSER ====================
    
    def parse_zeek(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Zeek logs (conn, dns, http, ssl, etc.)
        Example: DNS query for cyberfortress.local
        """
        source = log.get('_source', log)
        zeek = source.get('zeek', {})
        dataset = source.get('data_stream', {}).get('dataset', '')
        
        # Detect Zeek log type (dns, conn, http, etc.)
        zeek_log_type = dataset.replace('zeek.', '') if 'zeek.' in dataset else 'unknown'
        
        parsed = {
            'log_type': 'zeek',
            'zeek_log_type': zeek_log_type,
            'timestamp': source.get('@timestamp'),
            'session_id': zeek.get('session_id'),
            
            # Network 5-tuple
            'src_ip': source.get('source', {}).get('ip'),
            'src_port': source.get('source', {}).get('port'),
            'dest_ip': source.get('destination', {}).get('ip'),
            'dest_port': source.get('destination', {}).get('port'),
            'protocol': source.get('network', {}).get('protocol'),
            
            'community_id': source.get('network', {}).get('community_id'),
            'event_outcome': source.get('event', {}).get('outcome'),
        }
        
        # Protocol-specific parsing
        if zeek_log_type == 'dns':
            zeek_dns = zeek.get('dns', {})
            parsed['dns'] = {
                'query': zeek_dns.get('query'),
                'qtype': zeek_dns.get('qtype_name'),
                'rcode': zeek_dns.get('rcode_name'),
                'answers': zeek_dns.get('answers', []),
                'rejected': zeek_dns.get('rejected', False)
            }
        elif zeek_log_type == 'conn':
            zeek_conn = zeek.get('connection', {})
            parsed['connection'] = {
                'state': zeek_conn.get('state'),
                'duration': source.get('event', {}).get('duration'),
                'bytes_sent': zeek_conn.get('orig_bytes'),
                'bytes_recv': zeek_conn.get('resp_bytes'),
                'packets_sent': zeek_conn.get('orig_pkts'),
                'packets_recv': zeek_conn.get('resp_pkts')
            }
        elif zeek_log_type == 'http':
            zeek_http = zeek.get('http', {})
            parsed['http'] = {
                'method': zeek_http.get('method'),
                'host': zeek_http.get('host'),
                'uri': zeek_http.get('uri'),
                'status_code': zeek_http.get('status_code'),
                'user_agent': zeek_http.get('user_agent')
            }
        
        return parsed
    
    # ==================== WAZUH PARSER ====================
    
    def parse_wazuh(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Wazuh alerts (FIM, vulnerability detection, compliance, etc.)
        Example: Registry value deletion detected
        """
        source = log.get('_source', log)
        rule = source.get('rule', {})
        
        return {
            'log_type': 'wazuh',
            'timestamp': source.get('@timestamp') or source.get('timestamp'),
            
            # Agent info
            'agent': {
                'id': source.get('agent', {}).get('id'),
                'name': source.get('agent', {}).get('name'),
                'ip': source.get('agent', {}).get('ip')
            },
            
            # Rule details
            'rule_id': rule.get('id'),
            'rule_level': rule.get('level', 0),
            'rule_description': rule.get('description'),
            'rule_groups': rule.get('groups', []),
            
            # MITRE ATT&CK mapping
            'mitre': {
                'tactics': rule.get('mitre', {}).get('tactic', []),
                'techniques': rule.get('mitre', {}).get('technique', []),
                'technique_ids': rule.get('mitre', {}).get('id', [])
            },
            
            # Compliance frameworks
            'compliance': {
                'pci_dss': rule.get('pci_dss', []),
                'hipaa': rule.get('hipaa', []),
                'gdpr': rule.get('gdpr', []),
                'nist_800_53': rule.get('nist_800_53', [])
            },
            
            # Event-specific data
            'syscheck': source.get('syscheck', {}),  # FIM events
            'vulnerability': source.get('vulnerability', {}),  # Vuln scan
            'data': source.get('data', {}),  # Custom data fields
            
            # Windows-specific
            'windows': {
                'event_id': source.get('data', {}).get('win', {}).get('system', {}).get('eventID'),
                'channel': source.get('data', {}).get('win', {}).get('system', {}).get('channel')
            },
            
            'decoder': source.get('decoder', {}).get('name'),
            'location': source.get('location'),
            'full_log': source.get('full_log'),
            
            '_raw': {
                'id': source.get('id')
            }
        }
    
    # ==================== pfSENSE PARSER ====================
    
    def parse_pfsense(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse pfSense firewall logs (filterlog)
        Example: Blocked ICMP request from internal to external
        """
        source = log.get('_source', log)
        pfsense = source.get('pfsense', {})
        
        return {
            'log_type': 'pfsense',
            'timestamp': source.get('@timestamp'),
            
            # Firewall action
            'action': source.get('event', {}).get('action'),  # block/pass
            'reason': source.get('event', {}).get('reason'),  # match/default
            'direction': source.get('network', {}).get('direction'),  # inbound/outbound
            
            # Network 5-tuple
            'src_ip': source.get('source', {}).get('ip'),
            'dest_ip': source.get('destination', {}).get('ip'),
            'protocol': source.get('network', {}).get('transport'),
            
            # Firewall details
            'rule_id': source.get('rule', {}).get('id'),
            'interface': source.get('observer', {}).get('ingress', {}).get('interface', {}).get('name'),
            
            # Protocol-specific
            'icmp': pfsense.get('icmp', {}),
            'tcp': pfsense.get('tcp', {}),
            'udp': pfsense.get('udp', {}),
            
            # IP header info
            'ip_flags': pfsense.get('ip', {}).get('flags'),
            'ip_ttl': pfsense.get('ip', {}).get('ttl'),
            'ip_tos': pfsense.get('ip', {}).get('tos'),
            
            # Observer
            'firewall_name': source.get('observer', {}).get('name'),
            'community_id': source.get('network', {}).get('community_id'),
            
            '_raw': {
                'message': source.get('message')
            }
        }
    
    # ==================== PACKETBEAT/ROUTER PARSER ====================
    
    def parse_packetbeat(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Packetbeat network flow logs
        Example: TCP flow from attacker to NAT gateway
        """
        source = log.get('_source', log)
        flow = source.get('network_traffic', {}).get('flow', {})
        
        return {
            'log_type': 'packetbeat',
            'timestamp': source.get('@timestamp'),
            
            # Flow metadata
            'flow_id': flow.get('id'),
            'flow_final': flow.get('final', False),
            
            # Network 5-tuple
            'src_ip': source.get('source', {}).get('ip'),
            'src_port': source.get('source', {}).get('port'),
            'dest_ip': source.get('destination', {}).get('ip'),
            'dest_port': source.get('destination', {}).get('port'),
            'protocol': source.get('network', {}).get('transport'),
            
            # Traffic statistics
            'bytes_src': source.get('source', {}).get('bytes'),
            'bytes_dst': source.get('destination', {}).get('bytes'),
            'bytes_total': source.get('network', {}).get('bytes'),
            'packets_src': source.get('source', {}).get('packets'),
            'packets_dst': source.get('destination', {}).get('packets'),
            'packets_total': source.get('network', {}).get('packets'),
            
            # Timing
            'duration': source.get('event', {}).get('duration'),
            'start_time': source.get('event', {}).get('start'),
            'end_time': source.get('event', {}).get('end'),
            
            # Host context
            'host': {
                'name': source.get('host', {}).get('name'),
                'hostname': source.get('host', {}).get('hostname'),
                'ip': source.get('host', {}).get('ip', []),
                'mac': source.get('host', {}).get('mac', [])
            },
            
            'community_id': source.get('network', {}).get('community_id')
        }
    
    # ==================== MODSECURITY PARSER ====================
    
    def parse_modsecurity(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse ModSecurity WAF logs
        Handles OWASP Core Rule Set (CRS) alerts
        """
        source = log.get('_source', log)
        modsec = source.get('modsecurity', {})
        
        return {
            'log_type': 'modsecurity',
            'timestamp': source.get('@timestamp'),
            
            # WAF action
            'action': modsec.get('action'),  # block/allow/log
            'severity': modsec.get('severity'),
            
            # Attack detection
            'rule_id': modsec.get('rule_id'),
            'rule_msg': modsec.get('msg'),
            'tags': modsec.get('tags', []),  # OWASP_CRS, SQLi, XSS, etc.
            
            # HTTP request
            'http': {
                'method': source.get('http', {}).get('request', {}).get('method'),
                'uri': source.get('url', {}).get('original'),
                'host': source.get('url', {}).get('domain'),
                'user_agent': source.get('user_agent', {}).get('original'),
                'status_code': source.get('http', {}).get('response', {}).get('status_code')
            },
            
            # Network
            'src_ip': source.get('source', {}).get('ip'),
            'dest_ip': source.get('destination', {}).get('ip'),
            
            # Attack payload
            'matched_data': modsec.get('matched_data'),
            'matched_var': modsec.get('matched_var_name'),
            
            '_raw': modsec
        }
    
    # ==================== GENERIC PARSER ====================
    
    def parse_generic(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback parser for unknown log types
        Extracts common ECS fields
        """
        source = log.get('_source', log)
        
        return {
            'log_type': 'generic',
            'timestamp': source.get('@timestamp'),
            'message': source.get('message'),
            'event': source.get('event', {}),
            'source': source.get('source', {}),
            'destination': source.get('destination', {}),
            'network': source.get('network', {}),
            'host': source.get('host', {}),
            '_raw': source
        }
    
    # ==================== UTILITY FUNCTIONS ====================
    
    def extract_iocs(self, parsed_log: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Extract Indicators of Compromise (IOCs) from parsed log
        
        Returns:
            {
                'ips': [...],
                'domains': [...],
                'urls': [...],
                'hashes': [...],
                'emails': [...]
            }
        """
        iocs = {
            'ips': [],
            'domains': [],
            'urls': [],
            'hashes': [],
            'emails': []
        }
        
        # Extract IPs
        if parsed_log.get('src_ip'):
            iocs['ips'].append(parsed_log['src_ip'])
        if parsed_log.get('dest_ip'):
            iocs['ips'].append(parsed_log['dest_ip'])
        
        # Extract domains (DNS queries, HTTP hosts, etc.)
        if parsed_log.get('dns', {}).get('query'):
            iocs['domains'].append(parsed_log['dns']['query'])
        if parsed_log.get('http', {}).get('host'):
            iocs['domains'].append(parsed_log['http']['host'])
        
        # Extract URLs
        if parsed_log.get('http', {}).get('uri'):
            host = parsed_log.get('http', {}).get('host', '')
            uri = parsed_log['http']['uri']
            iocs['urls'].append(f"http://{host}{uri}")
        
        # Extract file hashes (from Wazuh FIM)
        syscheck = parsed_log.get('syscheck', {})
        for hash_field in ['md5_after', 'sha1_after', 'sha256_after']:
            if syscheck.get(hash_field):
                iocs['hashes'].append(syscheck[hash_field])
        
        # Remove duplicates
        for key in iocs:
            iocs[key] = list(set(iocs[key]))
        
        return iocs
    
    def is_high_severity(self, parsed_log: Dict[str, Any]) -> bool:
        """
        Quick severity check
        Returns True if log is high/critical severity
        """
        # Suricata: severity 1 = high
        if parsed_log.get('log_type') == 'suricata' and parsed_log.get('severity', 0) <= 2:
            return True
        
        # Wazuh: level >= 7 is high
        if parsed_log.get('log_type') == 'wazuh' and parsed_log.get('rule_level', 0) >= 7:
            return True
        
        # pfSense: blocked traffic from untrusted zone
        if parsed_log.get('log_type') == 'pfsense' and parsed_log.get('action') == 'block':
            return True
        
        return False


# ==================== FACTORY FUNCTION ====================

_global_parser: Optional[LogParser] = None

def get_parser() -> LogParser:
    """
    Get singleton parser instance
    
    Returns:
        LogParser instance
    """
    global _global_parser
    if _global_parser is None:
        _global_parser = LogParser()
    return _global_parser


# ==================== CONVENIENCE FUNCTIONS ====================

def parse_log(log: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quick parse function for single log
    Auto-detects type and parses
    """
    parser = get_parser()
    return parser.parse(log)


def parse_logs(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch parse multiple logs
    """
    parser = get_parser()
    return [parser.parse(log) for log in logs]
