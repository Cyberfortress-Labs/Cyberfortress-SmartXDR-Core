"""
Tests for Alert Summarization Service
Tests ML-classified alert querying, grouping, and risk scoring
"""
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from app.services.alert_summarization_service import AlertSummarizationService
from app.config import (
    ALERT_TIME_WINDOW,
    ALERT_MIN_PROBABILITY,
    RISK_SCORE_COUNT_WEIGHT,
    RISK_SCORE_PROBABILITY_WEIGHT,
    RISK_SCORE_SEVERITY_WEIGHT,
    RISK_SCORE_ESCALATION_WEIGHT
)


class TestAlertSummarizationService(unittest.TestCase):
    """Test Alert Summarization Service"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.service = AlertSummarizationService()
    
    def test_singleton_instance(self):
        """Test that service uses singleton pattern"""
        service1 = AlertSummarizationService()
        service2 = AlertSummarizationService()
        self.assertIs(service1, service2, "Should return same instance")
    
    def test_severity_levels_mapping(self):
        """Test severity level mapping"""
        self.assertEqual(self.service.SEVERITY_LEVELS["INFO"], 1)
        self.assertEqual(self.service.SEVERITY_LEVELS["WARNING"], 2)
        self.assertEqual(self.service.SEVERITY_LEVELS["ERROR"], 3)
    
    def test_pattern_detection(self):
        """Test attack pattern detection from ml_input"""
        test_cases = [
            ("nmap scan detected", "reconnaissance"),
            ("brute force attack", "brute_force"),
            ("lateral movement detected", "lateral_movement"),
            ("data exfiltration attempt", "exfiltration"),
            ("unknown threat", "unknown")
        ]
        
        for ml_input, expected_pattern in test_cases:
            pattern = self.service._detect_pattern(ml_input)
            self.assertEqual(pattern, expected_pattern, f"Failed for: {ml_input}")
    
    def test_escalation_detection_no_pattern(self):
        """Test escalation detection with no patterns"""
        grouped_alerts = [
            {"pattern": "unknown", "severity": "INFO"},
            {"pattern": "unknown", "severity": "INFO"}
        ]
        escalation = self.service._detect_escalation(grouped_alerts)
        self.assertEqual(escalation, 0.0, "No pattern should return 0")
    
    def test_escalation_detection_single_pattern(self):
        """Test escalation detection with single pattern"""
        grouped_alerts = [
            {"pattern": "reconnaissance", "severity": "WARNING"},
            {"pattern": "reconnaissance", "severity": "WARNING"}
        ]
        escalation = self.service._detect_escalation(grouped_alerts)
        self.assertEqual(escalation, 1.0, "Single pattern should return 1.0")
    
    def test_escalation_detection_sequence(self):
        """Test escalation detection with attack sequence"""
        grouped_alerts = [
            {"pattern": "reconnaissance", "severity": "WARNING"},
            {"pattern": "brute_force", "severity": "ERROR"},
            {"pattern": "lateral_movement", "severity": "ERROR"}
        ]
        escalation = self.service._detect_escalation(grouped_alerts)
        self.assertEqual(escalation, 2.0, "Attack sequence should return 2.0")
    
    def test_build_alert_context(self):
        """Test building alert context for summary"""
        grouped_alerts = [
            {
                "group_key": "192.168.1.1_reconnaissance_WARNING",
                "source_ip": "192.168.1.1",
                "pattern": "reconnaissance",
                "severity": "WARNING",
                "alert_count": 5,
                "avg_probability": 0.92,
                "agents": ["suricata"],
                "sample_alerts": [{"ml_input": "nmap scan detected", "message": "test"}]
            }
        ]
        
        context = self.service._build_alert_context(grouped_alerts, 65.5)
        
        self.assertIn("ML Alert Summary Context", context)
        self.assertIn("192.168.1.1", context)
        self.assertIn("reconnaissance", context)
        self.assertIn("65.5", context)
    
    def test_build_detailed_summary(self):
        """Test building detailed summary from alerts"""
        grouped_alerts = [
            {
                "group_key": "192.168.1.1_reconnaissance_WARNING",
                "source_ip": "192.168.1.1",
                "pattern": "reconnaissance",
                "severity": "WARNING",
                "alert_count": 5,
                "avg_probability": 0.92,
                "agents": ["suricata"],
                "sample_alerts": [{"ml_input": "nmap scan detected", "message": "test"}]
            }
        ]
        alert_context = self.service._build_alert_context(grouped_alerts, 65.5)
        
        summary = self.service._build_detailed_summary(alert_context, grouped_alerts, 65.5)
        
        self.assertIsNotNone(summary)
        self.assertIn("Risk Assessment", summary)
        self.assertIn("RECONNAISSANCE", summary.upper())
        self.assertIn("65.5", summary)
    
    def test_risk_score_zero_alerts(self):
        """Test risk score calculation with no alerts"""
        risk_score = self.service._calculate_risk_score([])
        self.assertEqual(risk_score, 0.0)
    
    def test_risk_score_single_alert_group(self):
        """Test risk score calculation with single alert group"""
        grouped_alerts = [
            {
                "alert_count": 5,
                "avg_probability": 0.9,
                "severity": "WARNING",
                "pattern": "reconnaissance"
            }
        ]
        
        risk_score = self.service._calculate_risk_score(grouped_alerts)
        
        # Should be > 0 and <= 100
        self.assertGreater(risk_score, 0)
        self.assertLessEqual(risk_score, 100)
    
    def test_risk_score_multiple_alert_groups(self):
        """Test risk score with multiple alert groups"""
        grouped_alerts = [
            {
                "alert_count": 10,
                "avg_probability": 0.95,
                "severity": "ERROR",
                "pattern": "lateral_movement"
            },
            {
                "alert_count": 5,
                "avg_probability": 0.85,
                "severity": "WARNING",
                "pattern": "brute_force"
            },
            {
                "alert_count": 2,
                "avg_probability": 0.75,
                "severity": "INFO",
                "pattern": "reconnaissance"
            }
        ]
        
        risk_score = self.service._calculate_risk_score(grouped_alerts)
        
        # Multiple groups should have higher risk
        self.assertGreater(risk_score, 30)
        self.assertLessEqual(risk_score, 100)
    
    def test_group_alerts_by_source_ip(self):
        """Test grouping alerts by source IP"""
        alerts = [
            {
                "source.ip": "192.168.1.1",
                "ml.prediction.predicted_value": "WARNING",
                "ml.prediction.prediction_probability": 0.9,
                "agent.name": "suricata",
                "ml_input": "nmap scan",
                "@timestamp": "2024-01-01T10:00:00Z",
                "message": "test1"
            },
            {
                "source.ip": "192.168.1.1",
                "ml.prediction.predicted_value": "WARNING",
                "ml.prediction.prediction_probability": 0.92,
                "agent.name": "zeek",
                "ml_input": "nmap scan",
                "@timestamp": "2024-01-01T10:01:00Z",
                "message": "test2"
            },
            {
                "source.ip": "192.168.1.2",
                "ml.prediction.predicted_value": "ERROR",
                "ml.prediction.prediction_probability": 0.95,
                "agent.name": "suricata",
                "ml_input": "brute force attack",
                "@timestamp": "2024-01-01T10:02:00Z",
                "message": "test3"
            }
        ]
        
        grouped = self.service._group_alerts(alerts, time_window_minutes=10)
        
        # Should have at least 2 groups (different IPs or patterns)
        self.assertGreaterEqual(len(grouped), 2)
        
        # Check first group
        first_group = grouped[0]
        self.assertIn("source_ip", first_group)
        self.assertIn("pattern", first_group)
        self.assertIn("alert_count", first_group)
        self.assertIn("avg_probability", first_group)
    
    
    def test_build_summary_prompt(self):
        """Test building detailed summary (replaces LLM prompt)"""
        grouped_alerts = [
            {
                "group_key": "192.168.1.1_reconnaissance_WARNING",
                "source_ip": "192.168.1.1",
                "pattern": "reconnaissance",
                "severity": "WARNING",
                "alert_count": 5,
                "avg_probability": 0.92,
                "agents": ["suricata"],
                "sample_alerts": [{"ml_input": "nmap scan detected"}]
            }
        ]
        alert_context = self.service._build_alert_context(grouped_alerts, 65.5)
        
        summary = self.service._build_detailed_summary(alert_context, grouped_alerts, 65.5)
        
        self.assertIn("Risk Assessment", summary)
        self.assertIn("192.168.1.1", summary)
    
    def test_get_index_patterns(self):
        """Test getting Elasticsearch index patterns"""
        patterns = self.service._get_index_patterns()
        
        # Should return multiple patterns for each source type
        self.assertGreater(len(patterns), 0)
        
        # Should include common patterns
        pattern_str = str(patterns)
        self.assertIn("logs-", pattern_str)
        self.assertIn("*", pattern_str)
    
    def test_fallback_summary(self):
        """Test fallback summary generation"""
        grouped_alerts = [
            {
                "alert_count": 5,
                "severity": "ERROR",
                "pattern": "reconnaissance"
            },
            {
                "alert_count": 3,
                "severity": "WARNING",
                "pattern": "brute_force"
            }
        ]
        
        summary = self.service._build_fallback_summary(grouped_alerts)
        
        self.assertIsNotNone(summary)
        self.assertIn("alert", summary.lower())
        self.assertGreater(len(summary), 10)
    
    def test_fallback_summary_empty(self):
        """Test fallback summary with no alerts"""
        summary = self.service._build_fallback_summary([])
        
        self.assertEqual(summary, "No alerts to summarize.")
    
    @patch('app.services.alert_summarization_service.ElasticsearchService')
    @patch('app.services.alert_summarization_service.LLMService')
    def test_summarize_alerts_no_results(self, mock_llm, mock_es):
        """Test summarization when no alerts found"""
        # Mock ES to return no alerts
        mock_es_instance = Mock()
        mock_es_instance.client.search.return_value = {"hits": {"hits": []}}
        mock_es.return_value = mock_es_instance
        
        # Create new instance with mocked dependencies
        service = AlertSummarizationService()
        service.es_service = mock_es_instance
        
        result = service.summarize_alerts(time_window_minutes=10)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "no_alerts")
        self.assertEqual(result["count"], 0)


class TestAlertSummarizationIntegration(unittest.TestCase):
    """Integration tests for Alert Summarization"""
    
    def test_config_values(self):
        """Test that config values are properly set"""
        self.assertGreater(ALERT_TIME_WINDOW, 0)
        self.assertGreaterEqual(ALERT_MIN_PROBABILITY, 0.5)
        self.assertLess(ALERT_MIN_PROBABILITY, 1.0)
        
        # Risk weights should sum to 1.0
        total_weight = (
            RISK_SCORE_COUNT_WEIGHT +
            RISK_SCORE_PROBABILITY_WEIGHT +
            RISK_SCORE_SEVERITY_WEIGHT +
            RISK_SCORE_ESCALATION_WEIGHT
        )
        self.assertAlmostEqual(total_weight, 1.0, places=5)


def run_manual_test():
    """Manual test - requires running Elasticsearch and LLM service"""
    service = AlertSummarizationService()
    
    print("\n" + "="*80)
    print("MANUAL ALERT SUMMARIZATION TEST")
    print("="*80)
    
    # Test with default time window
    print("\n1. Testing summarization with default time window...")
    result = service.summarize_alerts()
    
    print(f"Status: {result.get('status')}")
    print(f"Success: {result.get('success')}")
    print(f"Alert Count: {result.get('count', 0)}")
    print(f"Risk Score: {result.get('risk_score', 0)}/100")
    
    if result.get('grouped_alerts'):
        print(f"\nTop Alert Groups:")
        for i, group in enumerate(result.get('grouped_alerts', [])[:3], 1):
            print(f"  {i}. {group['pattern'].upper()} - {group['alert_count']} alerts")
    
    print(f"\nSummary Preview:")
    summary = result.get('summary', '')
    if summary:
        print(summary[:200] + "..." if len(summary) > 200 else summary)
    
    print("\n" + "="*80)


if __name__ == '__main__':
    # Run unit tests
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Uncomment to run manual integration test:
    # run_manual_test()
