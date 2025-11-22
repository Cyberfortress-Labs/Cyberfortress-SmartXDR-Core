"""
Test Elasticsearch Service - Query alerts from dual alert systems

Tests query logic for:
1. ElastAlert2 (critical alerts)
2. Kibana Security Alerts (medium/low alerts with sampling)
3. Combined daily report data aggregation

Configuration:
Loads credentials from .env file:
- ELASTICSEARCH_HOSTS
- ELASTICSEARCH_USERNAME
- ELASTICSEARCH_PASSWORD
- ELASTICSEARCH_CA_CERT (optional, for self-signed certificates)
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from datetime import datetime
from dotenv import load_dotenv
from app.services.elasticsearch_service import ElasticsearchService

# Load environment variables
load_dotenv()


def test_elastalert_query():
    """Test querying ElastAlert2 critical alerts"""
    print("\n" + "="*80)
    print("TEST 1: ElastAlert2 Critical Alerts Query")
    print("="*80)
    
    # Initialize service - credentials loaded from .env
    es_service = ElasticsearchService()
    
    try:
        # Query last 24 hours
        result = es_service.get_elastalert_alerts(hours=24, max_alerts=100)
        
        print(f"\n  Retrieved: {len(result['alerts'])}")
        print(f"  Rules triggered: {len(result['summary']['rules_triggered'])}")
        print(f"\n  Rules: {', '.join(result['summary']['rules_triggered'][:5])}")
        
        if result['alerts']:
            print(f"\n  Sample Alert (most recent):")
            sample = result['alerts'][0]
            print(f"    Rule: {sample['rule_name']}")
            print(f"    Time: {sample['timestamp']}")
            print(f"    Matches: {sample['num_matches']}")
        
        # Save to file for inspection
        output_file = "logs/test-outputs/elastalert-query-result.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Full result saved to: {output_file}")
        
        return result
        
    except Exception as e:
        print(f"ERROR querying ElastAlert2: {e}")
        return None
    finally:
        es_service.close()


def test_kibana_alerts_query():
    """Test querying Kibana Security Alerts with sampling"""
    print("\n" + "="*80)
    print("TEST 2: Kibana Security Alerts Query (Smart Sampling)")
    print("="*80)
    
    # Initialize service - credentials loaded from .env
    es_service = ElasticsearchService()
    
    try:
        # Query with custom sampling rates
        result = es_service.get_kibana_security_alerts(
            hours=24,
            severity_filter=["critical", "high", "medium", "low"],
            sample_rate={
                "critical": 1.0,   # 100% critical
                "high": 1.0,       # 100% high
                "medium": 0.2,     # 20% medium
                "low": 0.0         # 0% low (count only)
            },
            max_alerts=500
        )
        
        print(f"\n[OK] Kibana Alerts Query Result:")
        print(f"  Total by severity:")
        for severity, count in result['total_by_severity'].items():
            print(f"    {severity}: {count}")
        
        print(f"\n  Sampling applied:")
        for severity, info in result['summary']['sampling_applied'].items():
            print(f"    {severity}: {info}")
        
        print(f"\n  Total sampled alerts: {len(result['sampled_alerts'])}")
        
        print(f"\n  Top 5 triggered rules:")
        for rule in result['summary']['top_rules'][:5]:
            print(f"    {rule['rule']}: {rule['count']} times")
        
        if result['sampled_alerts']:
            print(f"\n  Sample Alert (highest risk):")
            sample = result['sampled_alerts'][0]
            print(f"    Rule: {sample['rule_name']}")
            print(f"    Severity: {sample['severity']} (Risk: {sample['risk_score']})")
            print(f"    Time: {sample['timestamp']}")
            print(f"    Source IP: {sample.get('source_ip', 'N/A')}")
        
        # Save to file
        output_file = "logs/test-outputs/kibana-alerts-query-result.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Full result saved to: {output_file}")
        
        return result
        
    except Exception as e:
        print(f"ERROR querying Kibana alerts: {e}")
        return None
    finally:
        es_service.close()


def test_aggregated_statistics():
    """Test aggregated security statistics"""
    print("\n" + "="*80)
    print("TEST 3: Aggregated Security Statistics")
    print("="*80)
    
    # Initialize service - credentials loaded from .env
    es_service = ElasticsearchService()
    
    try:
        result = es_service.get_aggregated_statistics(hours=24)
        
        print(f"\n[OK] Aggregated Statistics:")
        print(f"  Total events: {result['traffic_stats']['total_events']:,}")
        
        print(f"\n  Top 5 Attacked IPs:")
        for ip_data in result['top_attacked_ips'][:5]:
            print(f"    {ip_data['ip']}: {ip_data['hits']:,} hits")
        
        print(f"\n  Top 5 Attacker IPs:")
        for ip_data in result['top_attacker_ips'][:5]:
            print(f"    {ip_data['ip']}: {ip_data['hits']:,} hits")
        
        print(f"\n  Event Distribution:")
        for category, count in list(result['event_distribution'].items())[:5]:
            print(f"    {category}: {count:,}")
        
        print(f"\n  Top 5 Actions:")
        for action in result['traffic_stats']['top_actions'][:5]:
            print(f"    {action['action']}: {action['count']:,}")
        
        # Save to file
        output_file = "logs/test-outputs/aggregated-statistics-result.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Full result saved to: {output_file}")
        
        return result
        
    except Exception as e:
        print(f"ERROR getting aggregated statistics: {e}")
        return None
    finally:
        es_service.close()


def test_combined_daily_report():
    """Test combined data for daily intelligence report"""
    print("\n" + "="*80)
    print("TEST 4: Combined Daily Report Data")
    print("="*80)
    
    # Initialize service - credentials loaded from .env
    es_service = ElasticsearchService()
    
    try:
        # Get all data for daily report
        result = es_service.get_combined_alerts_for_daily_report(hours=24)
        
        print(f"\nCombined Daily Report Data:")
        print(f"  Generated at: {result['metadata']['generated_at']}")
        print(f"  Time range: {result['metadata']['time_range_hours']} hours")
        
        print(f"\n  Alert Summary:")
        print(f"    Total alerts detected: {result['metadata']['total_alert_count']:,}")
        print(f"    ElastAlert2 (critical): {result['metadata']['elastalert_count']}")
        print(f"    Kibana alerts (all severities): {result['metadata']['kibana_alert_count']:,}")
        print(f"    Sampled for AI analysis: {result['metadata']['sampled_alert_count']}")
        
        print(f"\n  ElastAlert2 Rules Triggered:")
        for rule in result['elastalert']['summary']['rules_triggered'][:5]:
            count = result['elastalert']['summary']['count_by_rule'][rule]
            print(f"    {rule}: {count} times")
        
        print(f"\n  Kibana Severity Distribution:")
        for severity, count in result['kibana_alerts']['total_by_severity'].items():
            print(f"    {severity}: {count:,}")
        
        print(f"\n  Traffic Context:")
        print(f"    Total events: {result['statistics']['traffic_stats']['total_events']:,}")
        print(f"    Top attacked IP: {result['statistics']['top_attacked_ips'][0]['ip']} "
              f"({result['statistics']['top_attacked_ips'][0]['hits']:,} hits)")
        
        # Calculate data reduction
        total_events = result['statistics']['traffic_stats']['total_events']
        alerts_sent_to_ai = (
            result['metadata']['elastalert_count'] +
            result['metadata']['sampled_alert_count']
        )
        
        if total_events > 0:
            reduction_rate = (1 - alerts_sent_to_ai / total_events) * 100
            print(f"\n  Data Reduction:")
            print(f"    Raw events: {total_events:,}")
            print(f"    Sent to AI: {alerts_sent_to_ai}")
            print(f"    Reduction: {reduction_rate:.2f}%")
        
        # Save complete report data
        output_file = "logs/test-outputs/daily-report-combined-data.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nFull report data saved to: {output_file}")
        
        # Also save a summary for quick viewing
        summary = {
            "metadata": result['metadata'],
            "elastalert_summary": result['elastalert']['summary'],
            "kibana_summary": result['kibana_alerts']['summary'],
            "statistics_summary": {
                "total_events": result['statistics']['traffic_stats']['total_events'],
                "top_5_attacked_ips": result['statistics']['top_attacked_ips'][:5],
                "top_5_attackers": result['statistics']['top_attacker_ips'][:5]
            }
        }
        
        summary_file = "logs/test-outputs/daily-report-summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Summary saved to: {summary_file}")
        
        return result
        
    except Exception as e:
        print(f"Error generating combined report: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        es_service.close()


if __name__ == "__main__":
    print("\n" + "ELASTICSEARCH SERVICE TESTS - Dual Alert System Query")
    print("Testing queries for ElastAlert2 + Kibana Security Alerts\n")
    
    # Check if .env file exists
    if not os.path.exists('.env'):
        print("WARNING SETUP REQUIRED:")
        print("   1. Copy .env.example to .env")
        print("   2. Set ELASTICSEARCH_PASSWORD in .env file")
        print("   3. Optionally set ELASTICSEARCH_CA_CERT for self-signed certificates")
        print()
    else:
        # Check if password is set
        password = os.getenv('ELASTICSEARCH_PASSWORD')
        if not password:
            print("WARNING ERROR: ELASTICSEARCH_PASSWORD not set in .env file")
            print()
        else:
            print("OK Configuration loaded from .env file")
            ca_cert = os.getenv('ELASTICSEARCH_CA_CERT')
            if ca_cert and os.path.isfile(ca_cert):
                print(f"OK Using CA certificate: {ca_cert}")
            else:
                print("WARNING No CA certificate configured (SSL verification disabled)")
            print()
    
    # Uncomment tests to run:
    
    # Test 1: ElastAlert2 critical alerts
    test_elastalert_query()
    
    # Test 2: Kibana security alerts with sampling
    test_kibana_alerts_query()
    
    # Test 3: Aggregated statistics
    test_aggregated_statistics()
    
    # Test 4: Combined daily report data
    test_combined_daily_report()
    
    print("\n" + "="*80)
    print("NEXT STEPS:")
    print("="*80)
    print("1. Configure .env file with Elasticsearch credentials")
    print("2. (Optional) Add ELASTICSEARCH_CA_CERT path for self-signed cert")
    print("3. Uncomment the test you want to run")
    print("4. Run: python tests/test_elasticsearch_service.py")
    print("5. Check results in logs/test-outputs/")
    print()
    print("Query Strategy:")
    print("   - ElastAlert2: 100% of critical alerts (already filtered)")
    print("   - Kibana: Smart sampling (100% high, 20% medium, count low)")
    print("   - Statistics: Aggregations for context (top IPs, events)")
    print()
