"""
Elasticsearch Service - Query alerts from ElastAlert2 and Kibana Security Alerts

Architecture:
- ElastAlert2 (elastalert_status*): Critical alerts requiring immediate response
- Kibana Alerts (.internal.alerts-security.alerts-default-*): Medium/low severity detection

Strategy:
- ElastAlert2: 100% of alerts (already filtered for critical events)
- Kibana Alerts: Smart sampling based on severity
  • 100% high severity
  • 20% medium severity
  • Count only for low severity
"""

import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError, NotFoundError

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class ElasticsearchService:
    """Service for querying alerts from Elasticsearch indices"""
    
    def __init__(
        self,
        hosts: Optional[List[str]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_certs: Optional[bool] = None,
        ca_certs: Optional[str] = None
    ):
        """
        Initialize Elasticsearch client
        
        Loads configuration from environment variables (.env file):
        - ELASTICSEARCH_HOSTS: Comma-separated list of ES nodes (default: https://192.168.100.128:9200)
        - ELASTICSEARCH_USERNAME: Auth username (default: elastic)
        - ELASTICSEARCH_PASSWORD: Auth password (required)
        - ELASTICSEARCH_CA_CERT: Path to CA certificate for self-signed certs (optional)
        
        Args:
            hosts: List of Elasticsearch nodes (overrides env var)
            username: Authentication username (overrides env var)
            password: Authentication password (overrides env var)
            verify_certs: Whether to verify SSL certificates (auto-detected from ca_certs)
            ca_certs: Path to CA certificate file (overrides env var)
        """
        # Load from environment variables with fallbacks
        if hosts is None:
            hosts_env = os.getenv('ELASTICSEARCH_HOSTS', 'https://192.168.100.128:9200')
            hosts = [h.strip() for h in hosts_env.split(',')]
        
        if username is None:
            username = os.getenv('ELASTICSEARCH_USERNAME', 'elastic')
        
        if password is None:
            password = os.getenv('ELASTICSEARCH_PASSWORD')
            if not password:
                raise ValueError(
                    "Elasticsearch password not provided. "
                    "Set ELASTICSEARCH_PASSWORD in .env file or pass as argument."
                )
        
        # Handle CA certificate for self-signed certs
        if ca_certs is None:
            ca_certs = os.getenv('ELASTICSEARCH_CA_CERT')
        
        # Auto-detect verify_certs based on CA cert availability
        if verify_certs is None:
            if ca_certs and os.path.isfile(ca_certs):
                verify_certs = True  # Trust self-signed cert via CA
                logger.info(f"Using CA certificate: {ca_certs}")
            else:
                verify_certs = False  # Disable SSL verification
                if ca_certs:
                    logger.warning(
                        f"CA certificate specified but not found: {ca_certs}. "
                        "SSL verification disabled."
                    )
                else:
                    logger.warning(
                        "No CA certificate provided. SSL verification disabled. "
                        "Set ELASTICSEARCH_CA_CERT in .env to enable secure connections."
                    )
        
        # Initialize Elasticsearch client
        es_config = {
            'hosts': hosts,
            'basic_auth': (username, password),
            'verify_certs': verify_certs,
            # Compatibility mode for ES 8.x with Python client 9.x
            'request_timeout': 30,
            'max_retries': 3,
            'retry_on_timeout': True
        }
        
        # Only add ca_certs if provided and file exists
        if verify_certs and ca_certs and os.path.isfile(ca_certs):
            es_config['ca_certs'] = ca_certs
        
        self.client = Elasticsearch(**es_config)
        
        # Test connection
        try:
            info = self.client.info()
            logger.info(f"Connected to Elasticsearch cluster: {info['cluster_name']}")
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")
            raise
    
    def get_elastalert_alerts(
        self,
        hours: int = 24,
        max_alerts: int = 1000
    ) -> Dict[str, Any]:
        """
        Query ElastAlert2 critical alerts from elastalert_status* index
        
        ElastAlert2 writes alerts to elastalert_status index with fields:
        - @timestamp: Alert timestamp
        - rule_name: Name of the triggered rule
        - match_body: The matched event data
        - alert_info: Alert metadata
        - alert_time: When alert was sent
        
        Args:
            hours: Time range to query (default: 24 hours)
            max_alerts: Maximum number of alerts to return
            
        Returns:
            {
                "total": int,
                "alerts": List[Dict],
                "summary": {
                    "time_range": str,
                    "rules_triggered": List[str],
                    "count_by_rule": Dict[str, int]
                }
            }
        """
        try:
            # Calculate time range
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            # Query elastalert_status index
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": start_time.isoformat(),
                                        "lte": end_time.isoformat()
                                    }
                                }
                            }
                        ],
                        "must_not": [
                            # Exclude ElastAlert2 internal errors/logs
                            {"term": {"alert_info.type": "elastalert_error"}}
                        ]
                    }
                },
                "sort": [
                    {"@timestamp": {"order": "desc"}}
                ],
                "size": max_alerts
            }
            
            response = self.client.search(
                index="elastalert_status*",
                body=query
            )
            
            # Parse alerts
            alerts = []
            rules_triggered = set()
            count_by_rule = {}
            
            for hit in response['hits']['hits']:
                source = hit['_source']
                rule_name = source.get('rule_name', 'Unknown')
                
                # Track statistics
                rules_triggered.add(rule_name)
                count_by_rule[rule_name] = count_by_rule.get(rule_name, 0) + 1
                
                # Extract alert details
                alert = {
                    "timestamp": source.get('@timestamp'),
                    "rule_name": rule_name,
                    "match_body": source.get('match_body', {}),
                    "alert_info": source.get('alert_info', {}),
                    "alert_time": source.get('alert_time'),
                    "num_hits": source.get('num_hits', 1),
                    "num_matches": source.get('num_matches', 1)
                }
                alerts.append(alert)
            
            result = {
                "total": response['hits']['total']['value'],
                "alerts": alerts,
                "summary": {
                    "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
                    "rules_triggered": sorted(list(rules_triggered)),
                    "count_by_rule": count_by_rule
                }
            }
            
            logger.info(
                f"Retrieved {len(alerts)} ElastAlert2 alerts "
                f"({len(rules_triggered)} unique rules triggered)"
            )
            
            return result
            
        except NotFoundError:
            logger.warning("elastalert_status* index not found - ElastAlert2 may not be configured")
            return {
                "total": 0,
                "alerts": [],
                "summary": {
                    "time_range": f"Last {hours} hours",
                    "rules_triggered": [],
                    "count_by_rule": {}
                }
            }
        except Exception as e:
            logger.error(f"Error querying ElastAlert2 alerts: {e}")
            raise
    
    def get_kibana_security_alerts(
        self,
        hours: int = 24,
        severity_filter: Optional[List[str]] = None,
        sample_rate: Optional[Dict[str, float]] = None,
        max_alerts: int = 1000
    ) -> Dict[str, Any]:
        """
        Query Kibana Security Alerts with smart sampling
        
        Kibana stores detection alerts in .internal.alerts-security.alerts-default-* index
        with ECS format + kibana.alert.* fields
        
        Strategy:
        - 100% critical/high severity (always include)
        - 20% medium severity (random sample to reduce noise)
        - Count only for low severity (statistical context)
        
        Args:
            hours: Time range to query
            severity_filter: List of severities to include (default: ["critical", "high", "medium"])
            sample_rate: Sampling rate per severity (default: {"high": 1.0, "medium": 0.2, "low": 0.0})
            max_alerts: Maximum alerts to return
            
        Returns:
            {
                "total_by_severity": Dict[str, int],
                "sampled_alerts": List[Dict],
                "summary": {
                    "time_range": str,
                    "top_rules": List[Dict],
                    "severity_distribution": Dict[str, int],
                    "sampling_applied": Dict[str, str]
                }
            }
        """
        try:
            # Default severity filter
            if severity_filter is None:
                severity_filter = ["critical", "high", "medium"]
            
            # Default sampling rates
            if sample_rate is None:
                sample_rate = {
                    "critical": 1.0,  # 100% critical
                    "high": 1.0,      # 100% high
                    "medium": 0.2,    # 20% medium
                    "low": 0.0        # 0% low (count only)
                }
            
            # Calculate time range
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            # First, get total count by severity
            severity_agg_query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": start_time.isoformat(),
                                        "lte": end_time.isoformat()
                                    }
                                }
                            }
                        ]
                    }
                },
                "size": 0,
                "aggs": {
                    "severity_distribution": {
                        "terms": {
                            "field": "kibana.alert.severity",
                            "size": 10
                        }
                    },
                    "top_rules": {
                        "terms": {
                            "field": "kibana.alert.rule.name",
                            "size": 20
                        }
                    }
                }
            }
            
            agg_response = self.client.search(
                index=".internal.alerts-security.alerts-default-*",
                body=severity_agg_query
            )
            
            # Parse aggregations
            total_by_severity = {}
            for bucket in agg_response['aggregations']['severity_distribution']['buckets']:
                total_by_severity[bucket['key']] = bucket['doc_count']
            
            top_rules = [
                {"rule": b['key'], "count": b['doc_count']}
                for b in agg_response['aggregations']['top_rules']['buckets']
            ]
            
            # Now query sampled alerts
            sampled_alerts = []
            
            for severity in severity_filter:
                rate = sample_rate.get(severity, 0.0)
                if rate <= 0:
                    continue  # Skip if sampling rate is 0
                
                # Calculate how many alerts to fetch for this severity
                total_count = total_by_severity.get(severity, 0)
                sample_size = int(total_count * rate)
                
                if sample_size == 0:
                    continue
                
                # Query alerts for this severity
                query = {
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "range": {
                                        "@timestamp": {
                                            "gte": start_time.isoformat(),
                                            "lte": end_time.isoformat()
                                        }
                                    }
                                },
                                {
                                    "term": {
                                        "kibana.alert.severity": severity
                                    }
                                }
                            ]
                        }
                    },
                    "sort": [
                        {"kibana.alert.risk_score": {"order": "desc"}},  # Prioritize high risk
                        {"@timestamp": {"order": "desc"}}
                    ],
                    "size": min(sample_size, max_alerts // len(severity_filter))
                }
                
                response = self.client.search(
                    index=".internal.alerts-security.alerts-default-*",
                    body=query
                )
                
                # Parse alerts
                for hit in response['hits']['hits']:
                    source = hit['_source']
                    kibana_alert = source.get('kibana', {}).get('alert', {})
                    
                    alert = {
                        "timestamp": source.get('@timestamp'),
                        "severity": kibana_alert.get('severity'),
                        "risk_score": kibana_alert.get('risk_score'),
                        "rule_name": kibana_alert.get('rule', {}).get('name'),
                        "rule_description": kibana_alert.get('rule', {}).get('description'),
                        "original_event": kibana_alert.get('original_event', {}),
                        "reason": kibana_alert.get('reason'),
                        "workflow_status": kibana_alert.get('workflow_status'),
                        # ECS fields
                        "source_ip": source.get('source', {}).get('ip'),
                        "destination_ip": source.get('destination', {}).get('ip'),
                        "host_name": source.get('host', {}).get('name'),
                        "user_name": source.get('user', {}).get('name'),
                        "event_category": source.get('event', {}).get('category'),
                        "event_action": source.get('event', {}).get('action')
                    }
                    sampled_alerts.append(alert)
            
            result = {
                "total_by_severity": total_by_severity,
                "sampled_alerts": sampled_alerts,
                "summary": {
                    "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
                    "top_rules": top_rules[:10],  # Top 10 most triggered rules
                    "severity_distribution": total_by_severity,
                    "sampling_applied": {
                        sev: f"{int(rate*100)}% ({total_by_severity.get(sev, 0)} total → {len([a for a in sampled_alerts if a['severity'] == sev])} sampled)"
                        for sev, rate in sample_rate.items()
                        if sev in total_by_severity
                    }
                }
            }
            
            logger.info(
                f"Retrieved Kibana alerts: "
                f"{sum(total_by_severity.values())} total → {len(sampled_alerts)} sampled"
            )
            
            return result
            
        except NotFoundError:
            logger.warning("Kibana security alerts index not found")
            return {
                "total_by_severity": {},
                "sampled_alerts": [],
                "summary": {
                    "time_range": f"Last {hours} hours",
                    "top_rules": [],
                    "severity_distribution": {},
                    "sampling_applied": {}
                }
            }
        except Exception as e:
            logger.error(f"Error querying Kibana security alerts: {e}")
            raise
    
    def get_aggregated_statistics(
        self,
        hours: int = 24,
        indices: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated security statistics from raw logs
        
        Provides context for daily report:
        - Top attacked IPs
        - Top attackers (source IPs)
        - Event distribution by type
        - Traffic statistics
        
        Args:
            hours: Time range for aggregation
            indices: Indices to query (default: common log indices)
            
        Returns:
            {
                "top_attacked_ips": List[Dict],
                "top_attacker_ips": List[Dict],
                "event_distribution": Dict[str, int],
                "traffic_stats": Dict[str, Any]
            }
        """
        try:
            # Default indices - common ECS log sources
            if indices is None:
                indices = [
                    "logs-*",
                    "filebeat-*",
                    "packetbeat-*",
                    "suricata-*",
                    "zeek-*"
                ]
            
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            # Aggregation query
            query = {
                "query": {
                    "range": {
                        "@timestamp": {
                            "gte": start_time.isoformat(),
                            "lte": end_time.isoformat()
                        }
                    }
                },
                "size": 0,
                "aggs": {
                    "top_destination_ips": {
                        "terms": {
                            "field": "destination.ip",
                            "size": 20
                        }
                    },
                    "top_source_ips": {
                        "terms": {
                            "field": "source.ip",
                            "size": 20
                        }
                    },
                    "event_categories": {
                        "terms": {
                            "field": "event.category",
                            "size": 15
                        }
                    },
                    "event_actions": {
                        "terms": {
                            "field": "event.action",
                            "size": 15
                        }
                    }
                }
            }
            
            response = self.client.search(
                index=indices,
                body=query,
                ignore_unavailable=True
            )
            
            # Parse aggregations
            result = {
                "top_attacked_ips": [
                    {"ip": b['key'], "hits": b['doc_count']}
                    for b in response['aggregations']['top_destination_ips']['buckets']
                ],
                "top_attacker_ips": [
                    {"ip": b['key'], "hits": b['doc_count']}
                    for b in response['aggregations']['top_source_ips']['buckets']
                ],
                "event_distribution": {
                    b['key']: b['doc_count']
                    for b in response['aggregations']['event_categories']['buckets']
                },
                "traffic_stats": {
                    "total_events": response['hits']['total']['value'],
                    "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
                    "top_actions": [
                        {"action": b['key'], "count": b['doc_count']}
                        for b in response['aggregations']['event_actions']['buckets']
                    ]
                }
            }
            
            logger.info(
                f"Aggregated statistics: {result['traffic_stats']['total_events']} total events"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting aggregated statistics: {e}")
            raise
    
    def get_ml_predictions(
        self,
        hours: int = 24,
        min_probability: float = 0.5,
        max_results: int = 1000,
        indices: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Query ML prediction results from log classification pipeline
        
        ML Pipeline outputs logs with severity predictions:
        - ml.prediction.predicted_value: INFO, WARNING, ERROR
        - ml.prediction.prediction_probability: Confidence score (0-1)
        
        Severity Levels:
        - INFO: Normal activity, no action needed
        - WARNING: Needs review, potential issue
        - ERROR: Requires immediate attention, likely incident
        
        Args:
            hours: Time range to query (default: 24)
            min_probability: Minimum prediction probability (default: 0.5)
            max_results: Maximum results to return per severity
            indices: Indices to query (default: logs-*, filebeat-*)
            
        Returns:
            {
                "total": int,
                "by_severity": {
                    "ERROR": {"count": int, "samples": [...]},
                    "WARNING": {"count": int, "samples": [...]},
                    "INFO": {"count": int, "samples": [...]}
                },
                "summary": {
                    "time_range": str,
                    "high_confidence_count": int,
                    "severity_distribution": {...}
                }
            }
        """
        try:
            if indices is None:
                indices = ["logs-*", "filebeat-*", "winlogbeat-*"]
            
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=hours)
            
            # Aggregation query - get distribution first
            agg_query = {
                "query": {
                    "bool": {
                        "must": [
                            {"exists": {"field": "ml.prediction.predicted_value"}},
                            {
                                "range": {
                                    "ml.prediction.prediction_probability": {
                                        "gt": min_probability
                                    }
                                }
                            },
                            {
                                "range": {
                                    "@timestamp": {
                                        "gte": start_time.isoformat(),
                                        "lte": end_time.isoformat()
                                    }
                                }
                            }
                        ]
                    }
                },
                "size": 0,
                "aggs": {
                    "severity_distribution": {
                        "terms": {
                            "field": "ml.prediction.predicted_value",
                            "size": 10
                        },
                        "aggs": {
                            "avg_probability": {
                                "avg": {"field": "ml.prediction.prediction_probability"}
                            },
                            "high_confidence": {
                                "filter": {
                                    "range": {
                                        "ml.prediction.prediction_probability": {"gte": 0.8}
                                    }
                                }
                            }
                        }
                    },
                    "probability_ranges": {
                        "range": {
                            "field": "ml.prediction.prediction_probability",
                            "ranges": [
                                {"key": "low", "from": 0.5, "to": 0.7},
                                {"key": "medium", "from": 0.7, "to": 0.9},
                                {"key": "high", "from": 0.9, "to": 1.0}
                            ]
                        }
                    }
                }
            }
            
            agg_response = self.client.search(
                index=indices,
                body=agg_query,
                ignore_unavailable=True
            )
            
            total_hits = agg_response['hits']['total']['value']
            
            # Parse severity distribution
            severity_distribution = {}
            high_confidence_count = 0
            
            for bucket in agg_response['aggregations']['severity_distribution']['buckets']:
                severity = bucket['key']
                count = bucket['doc_count']
                avg_prob = bucket['avg_probability']['value']
                high_conf = bucket['high_confidence']['doc_count']
                
                severity_distribution[severity] = {
                    "count": count,
                    "avg_probability": round(avg_prob, 3) if avg_prob else 0,
                    "high_confidence_count": high_conf
                }
                high_confidence_count += high_conf
            
            # Get sample logs for each severity (prioritize ERROR and WARNING)
            by_severity = {}
            
            for severity in ["ERROR", "WARNING", "INFO"]:
                # Adjust sample size based on severity importance
                sample_size = {
                    "ERROR": min(100, max_results),    # All ERROR logs
                    "WARNING": min(50, max_results // 2), # 50% WARNING
                    "INFO": min(20, max_results // 5)  # 20% INFO
                }.get(severity, 20)
                
                sample_query = {
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"ml.prediction.predicted_value": severity}},
                                {
                                    "range": {
                                        "ml.prediction.prediction_probability": {
                                            "gt": min_probability
                                        }
                                    }
                                },
                                {
                                    "range": {
                                        "@timestamp": {
                                            "gte": start_time.isoformat(),
                                            "lte": end_time.isoformat()
                                        }
                                    }
                                }
                            ]
                        }
                    },
                    "sort": [
                        {"ml.prediction.prediction_probability": {"order": "desc"}},
                        {"@timestamp": {"order": "desc"}}
                    ],
                    "size": sample_size,
                    "_source": [
                        "@timestamp",
                        "message",
                        "ml.prediction.predicted_value",
                        "ml.prediction.prediction_probability",
                        "source.ip",
                        "destination.ip",
                        "host.name",
                        "event.category",
                        "event.action",
                        "log.level",
                        "agent.type"
                    ]
                }
                
                sample_response = self.client.search(
                    index=indices,
                    body=sample_query,
                    ignore_unavailable=True
                )
                
                samples = []
                for hit in sample_response['hits']['hits']:
                    source = hit['_source']
                    ml_pred = source.get('ml', {}).get('prediction', {})
                    
                    sample = {
                        "timestamp": source.get('@timestamp'),
                        "message": source.get('message', '')[:500],  # Truncate long messages
                        "predicted_severity": ml_pred.get('predicted_value'),
                        "probability": ml_pred.get('prediction_probability'),
                        "source_ip": source.get('source', {}).get('ip'),
                        "destination_ip": source.get('destination', {}).get('ip'),
                        "host": source.get('host', {}).get('name'),
                        "event_category": source.get('event', {}).get('category'),
                        "event_action": source.get('event', {}).get('action'),
                        "log_level": source.get('log', {}).get('level'),
                        "agent_type": source.get('agent', {}).get('type')
                    }
                    samples.append(sample)
                
                by_severity[severity] = {
                    "count": severity_distribution.get(severity, {}).get('count', 0),
                    "avg_probability": severity_distribution.get(severity, {}).get('avg_probability', 0),
                    "samples": samples
                }
            
            result = {
                "total": total_hits,
                "by_severity": by_severity,
                "summary": {
                    "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
                    "min_probability_threshold": min_probability,
                    "high_confidence_count": high_confidence_count,
                    "severity_distribution": {
                        sev: data.get('count', 0) 
                        for sev, data in severity_distribution.items()
                    },
                    "probability_ranges": {
                        b['key']: b['doc_count']
                        for b in agg_response['aggregations']['probability_ranges']['buckets']
                    }
                }
            }
            
            logger.info(
                f"Retrieved ML predictions: {total_hits} total "
                f"ERROR: {by_severity.get('ERROR', {}).get('count', 0)}, "
                f"WARNING: {by_severity.get('WARNING', {}).get('count', 0)}, "
                f"INFO: {by_severity.get('INFO', {}).get('count', 0)})"
            )
            
            return result
            
        except NotFoundError:
            logger.warning("ML prediction indices not found")
            return {
                "total": 0,
                "by_severity": {},
                "summary": {
                    "time_range": f"Last {hours} hours",
                    "high_confidence_count": 0,
                    "severity_distribution": {}
                }
            }
        except Exception as e:
            logger.error(f"Error querying ML predictions: {e}")
            return {
                "total": 0,
                "by_severity": {},
                "summary": {"error": str(e)}
            }
    
    def get_combined_alerts_for_daily_report(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Combined method to get all data needed for daily intelligence report
        
        Combines:
        1. ElastAlert2 critical alerts (100%)
        2. Kibana security alerts (smart sampling)
        3. ML log classification predictions
        4. Aggregated statistics (context)
        
        Returns:
            {
                "elastalert": {...},
                "kibana_alerts": {...},
                "ml_predictions": {...},
                "statistics": {...},
                "metadata": {
                    "generated_at": str,
                    "time_range_hours": int,
                    "total_alert_count": int
                }
            }
        """
        logger.info(f"Generating combined alert data for {hours}h daily report")
        
        # Query all data sources
        elastalert = self.get_elastalert_alerts(hours=hours)
        kibana_alerts = self.get_kibana_security_alerts(hours=hours)
        ml_predictions = self.get_ml_predictions(hours=hours)
        statistics = self.get_aggregated_statistics(hours=hours)
        
        # Calculate totals
        kibana_total = sum(kibana_alerts['total_by_severity'].values())
        ml_eror_count = ml_predictions.get('by_severity', {}).get('ERROR', {}).get('count', 0)
        ml_warn_count = ml_predictions.get('by_severity', {}).get('WARNING', {}).get('count', 0)
        
        total_alerts = (
            elastalert['total'] +
            kibana_total +
            ml_eror_count + ml_warn_count  # Only count ERROR and WARNING from ML
        )
        
        result = {
            "elastalert": elastalert,
            "kibana_alerts": kibana_alerts,
            "ml_predictions": ml_predictions,
            "statistics": statistics,
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "time_range_hours": hours,
                "total_alert_count": total_alerts,
                "elastalert_count": elastalert['total'],
                "kibana_alert_count": kibana_total,
                "sampled_alert_count": len(kibana_alerts['sampled_alerts']),
                "ml_prediction_count": ml_predictions.get('total', 0),
                "ml_eror_count": ml_eror_count,
                "ml_warn_count": ml_warn_count
            }
        }
        
        logger.info(
            f"Combined report data ready: "
            f"{total_alerts} total alerts → "
            f"{elastalert['total']} ElastAlert2 + "
            f"{len(kibana_alerts['sampled_alerts'])} Kibana (sampled) + "
            f"{ml_eror_count} ML ERROR + {ml_warn_count} ML WARNING"
        )
        
        return result
    
    def close(self):
        """Close Elasticsearch client connection"""
        try:
            self.client.close()
            logger.info("Elasticsearch connection closed")
        except Exception as e:
            logger.error(f"Error closing Elasticsearch connection: {e}")
