"""
Alert Summarization Service - Analyze and summarize ML-classified alerts from Elasticsearch
"""
import json
import hashlib
import io
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import re

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from app.services.elasticsearch_service import ElasticsearchService
from app.services.llm_service import LLMService
from app.utils.logger import setup_logger
from app.config import (
    ALERT_TIME_WINDOW,
    ALERT_MIN_PROBABILITY,
    ALERT_MIN_SEVERITY,
    ALERT_SOURCE_TYPES,
    RISK_SCORE_COUNT_WEIGHT,
    RISK_SCORE_PROBABILITY_WEIGHT,
    RISK_SCORE_SEVERITY_WEIGHT,
    RISK_SCORE_ESCALATION_WEIGHT,
    DEBUG_MODE
)

logger = setup_logger(__name__)


class AlertSummarizationService:
    """Service để summarize và analyze ML-classified alerts từ Elasticsearch"""
    
    _instance = None
    
    # Severity level mapping
    SEVERITY_LEVELS = {
        "INFO": 1,
        "WARNING": 2,
        "ERROR": 3
    }
    
    # Attack pattern sequences for escalation detection
    ATTACK_PATTERNS = {
        "reconnaissance": ["nmap", "syn_scan", "port_scan", "network_scan", "nessus", "scan", "probe", "enum"],
        "brute_force": ["brute", "login_attempt", "password", "auth_failed", "unauthorized", "failed login", "authentication"],
        "lateral_movement": ["lateral", "move", "privilege", "escalation", "lateral_movement", "rdp", "smb"],
        "exfiltration": ["exfil", "download", "extract", "data_transfer", "upload", "ftp", "scp"],
        "network_attack": ["syn flood", "ddos", "dos", "flood", "amplification"],
        "malware": ["malware", "trojan", "virus", "ransomware", "exploit", "shellcode"],
        "web_attack": ["sql injection", "xss", "csrf", "lfi", "rfi", "command injection", "path traversal"],
        "blocked_traffic": ["block", "deny", "drop", "reject", "filtered"],
        "suspicious_traffic": ["suspicious", "anomaly", "unusual", "alert", "threat"]
    }
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize Alert Summarization Service"""
        if self._initialized:
            return
        
        self.es_service = ElasticsearchService()
        self.llm_service = LLMService()
        self._initialized = True
        
        # Log Elasticsearch status
        if self.es_service.enabled and self.es_service.client:
            logger.info("✓ Alert Summarization Service initialized with Elasticsearch")
        elif not self.es_service.enabled:
            logger.warning("⚠️  Alert Summarization Service initialized WITHOUT Elasticsearch (ELASTICSEARCH_ENABLED=false)")
        else:
            logger.error("❌ Alert Summarization Service initialized but Elasticsearch connection FAILED (check password/connection)")
    
    def summarize_alerts(self, time_window_minutes: Optional[int] = None, 
                        source_ip: Optional[str] = None) -> Dict[str, Any]:
        """
        Summarize ML-classified alerts from Elasticsearch
        
        Args:
            time_window_minutes: Time window for grouping (uses config default if None)
            source_ip: Filter by source IP (optional)
        
        Returns:
            Dict with summarized alerts, risk scores, and MITRE tags
        """
        try:
            if time_window_minutes is None:
                time_window_minutes = ALERT_TIME_WINDOW
            
            # Query Elasticsearch
            alerts = self._query_alerts(time_window_minutes, source_ip)
            
            if not alerts:
                return {
                    "success": True,
                    "status": "no_alerts",
                    "message": "No alerts found in the specified time window",
                    "count": 0,
                    "grouped_alerts": [],
                    "summary": "",
                    "risk_score": 0,
                    "time_window_minutes": time_window_minutes
                }
            
            # Group alerts
            grouped = self._group_alerts(alerts, time_window_minutes)
            
            # Calculate risk score
            risk_score = self._calculate_risk_score(grouped)
            
            # Generate LLM summary
            summary_text = self._generate_summary(grouped, risk_score)
            
            # Generate visualization (optional, returns base64 PNG or None)
            visualization = self.generate_visualization(grouped, risk_score)
            
            result = {
                "success": True,
                "status": "completed",
                "count": len(alerts),
                "grouped_alerts": grouped,
                "summary": summary_text,
                "risk_score": risk_score,
                "time_window_minutes": time_window_minutes,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if visualization:
                result["visualization"] = visualization
            
            return result
        
        except Exception as e:
            logger.error(f"❌ Alert summarization failed: {str(e)}")
            return {
                "success": False,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def generate_visualization(self, grouped_alerts: List[Dict], risk_score: float) -> Optional[str]:
        """
        Generate visualization charts for alert summary
        
        Returns:
            Base64-encoded PNG image or None if matplotlib not available
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("⚠ Matplotlib not available, skipping visualization")
            return None
        
        if not grouped_alerts:
            return None
        
        try:
            # Create figure with subplots
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))
            fig.suptitle(f'🚨 ML Alert Analysis Dashboard (Risk: {risk_score:.1f}/100)', 
                        fontsize=16, fontweight='bold')
            
            # 1. Pattern Distribution (Pie Chart)
            pattern_counts = Counter([g['pattern'] for g in grouped_alerts])
            patterns = list(pattern_counts.keys())
            counts = list(pattern_counts.values())
            colors = plt.get_cmap('Set3')(range(len(patterns)))
            
            ax1.pie(counts, labels=[p.replace('_', ' ').title() for p in patterns], 
                   autopct='%1.1f%%', colors=colors, startangle=90)
            ax1.set_title('Alert Distribution by Pattern', fontweight='bold')
            
            # 2. Top 10 Source IPs (Bar Chart)
            top_ips = sorted(grouped_alerts, key=lambda x: x['alert_count'], reverse=True)[:10]
            ip_labels = [g['source_ip'][:15] + '...' if len(g['source_ip']) > 15 else g['source_ip'] 
                        for g in top_ips]
            ip_counts = [g['alert_count'] for g in top_ips]
            
            bars = ax2.barh(ip_labels, ip_counts, color='coral')
            ax2.set_xlabel('Alert Count')
            ax2.set_title('Top 10 Affected IPs', fontweight='bold')
            ax2.invert_yaxis()
            
            # Add value labels on bars
            for i, (bar, count) in enumerate(zip(bars, ip_counts)):
                ax2.text(count + 0.5, i, str(count), va='center')
            
            # 3. Severity Distribution (Stacked Bar)
            severity_data = defaultdict(lambda: defaultdict(int))
            for g in grouped_alerts:
                severity_data[g['pattern']][g['severity']] += g['alert_count']
            
            patterns_for_stack = list(severity_data.keys())[:8]  # Top 8 patterns
            severities = ['INFO', 'WARNING', 'ERROR']
            severity_colors = {'INFO': '#4CAF50', 'WARNING': '#FF9800', 'ERROR': '#F44336'}
            
            x_pos = range(len(patterns_for_stack))
            bottoms = [0] * len(patterns_for_stack)
            
            for severity in severities:
                values = [severity_data[p].get(severity, 0) for p in patterns_for_stack]
                if any(values):  # Only plot if there's data
                    ax3.bar(x_pos, values, bottom=bottoms, 
                           label=severity, color=severity_colors[severity])
                    bottoms = [b + v for b, v in zip(bottoms, values)]
            
            ax3.set_xticks(x_pos)
            ax3.set_xticklabels([p.replace('_', ' ').title()[:12] for p in patterns_for_stack], 
                               rotation=45, ha='right')
            ax3.set_ylabel('Alert Count')
            ax3.set_title('Severity Distribution by Pattern', fontweight='bold')
            ax3.legend()
            
            # 4. Confidence Distribution (Box Plot)
            pattern_probs = defaultdict(list)
            for g in grouped_alerts:
                pattern_probs[g['pattern']].append(g['avg_probability'] * 100)
            
            patterns_for_box = list(pattern_probs.keys())[:8]
            prob_data = [pattern_probs[p] for p in patterns_for_box]
            
            bp = ax4.boxplot(prob_data, labels=[p.replace('_', ' ').title()[:12] 
                                                for p in patterns_for_box],
                            patch_artist=True)
            
            # Color boxes
            for patch in bp['boxes']:
                patch.set_facecolor('lightblue')
            
            ax4.set_xticklabels(ax4.get_xticklabels(), rotation=45, ha='right')
            ax4.set_ylabel('ML Confidence (%)')
            ax4.set_title('ML Confidence Distribution', fontweight='bold')
            ax4.grid(axis='y', alpha=0.3)
            
            plt.tight_layout()
            
            # Convert to base64
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
            buf.seek(0)
            img_base64 = base64.b64encode(buf.read()).decode('utf-8')
            plt.close(fig)
            
            return img_base64
            
        except Exception as e:
            logger.error(f"❌ Error generating visualization: {e}")
            return None
    
    def _query_alerts(self, time_window_minutes: int, source_ip: Optional[str]) -> List[Dict]:
        """Query Elasticsearch for ML-classified alerts"""
        try:
            # Check if Elasticsearch client is available
            if not self.es_service.enabled or self.es_service.client is None:
                logger.error("❌ Elasticsearch service not available. Check ELASTICSEARCH_PASSWORD in .env")
                return []
            
            # Build time range
            now = datetime.utcnow()
            start_time = now - timedelta(minutes=time_window_minutes)
            
            # Build query for all indices - include INFO, WARNING, ERROR
            must_clauses = [
                {"range": {"@timestamp": {"gte": start_time.isoformat(), "lte": now.isoformat()}}},
                {"terms": {"ml.prediction.predicted_value": ["INFO", "WARNING", "ERROR"]}},
                {"range": {"ml.prediction.prediction_probability": {"gte": ALERT_MIN_PROBABILITY}}},
                {"exists": {"field": "ml_input"}},  # Ensure ml_input exists (summary for user)
                {"bool": {"must_not": {"term": {"ml_input.keyword": ""}}}}  # Exclude empty ml_input
            ]
            
            if source_ip:
                must_clauses.append({"term": {"source.ip": source_ip}})
            
            query = {
                "query": {
                    "bool": {
                        "must": must_clauses
                    }
                },
                "size": 10000,  # Increased from 1000 to capture more alerts
                "_source": [
                    "ml_input",
                    "ml.prediction.predicted_value",
                    "ml.prediction.prediction_probability",
                    "agent.name",
                    "source.ip",
                    "destination.ip",
                    "event.module",
                    "event.action",
                    "message",
                    "@timestamp"
                ],
                "sort": [{"@timestamp": {"order": "desc"}}]  # Get most recent first
            }
            
            # Query all indices at once (more efficient and catches data streams)
            alerts = []
            try:
                response = self.es_service.client.search(index="*", body=query)
                alerts = [hit["_source"] for hit in response.get("hits", {}).get("hits", [])]
                
                if DEBUG_MODE:
                    logger.debug(f"📊 Found {len(alerts)} alerts in Elasticsearch")
            except Exception as e:
                logger.error(f"❌ Could not query Elasticsearch: {str(e)}")
            
            return alerts
        
        except Exception as e:
            logger.error(f"❌ ES query failed: {str(e)}")
            return []
    
    def _get_index_patterns(self) -> List[str]:
        """Get Elasticsearch index patterns for all source types"""
        patterns = []
        
        for source_type in ALERT_SOURCE_TYPES:
            # Try common patterns: logs-source_type-*, source_type-*, source_type
            patterns.extend([
                f"logs-{source_type}-*",
                f"{source_type}-*",
                source_type
            ])
        
        return patterns
    
    def _group_alerts(self, alerts: List[Dict], time_window_minutes: int) -> List[Dict]:
        """Group alerts by time window, source IP, and auto-detected patterns"""
        grouped = defaultdict(list)
        
        for alert in alerts:
            try:
                # Support both nested (source.ip) and flat (source_ip) field structures
                source_ip = alert.get("source", {}).get("ip") if isinstance(alert.get("source"), dict) else alert.get("source.ip", "unknown")
                if not source_ip or source_ip == "unknown":
                    source_ip = alert.get("source_ip", "unknown")
                
                # Get ML prediction values (nested structure)
                ml_pred = alert.get("ml", {}).get("prediction", {})
                severity = ml_pred.get("predicted_value", "INFO")
                probability = ml_pred.get("prediction_probability", 0)
                
                timestamp = alert.get("@timestamp", "")
                ml_input = alert.get("ml_input", "")
                
                # Get agent name (nested structure)
                agent_name = alert.get("agent", {}).get("name", "unknown") if isinstance(alert.get("agent"), dict) else alert.get("agent.name", "unknown")
                
                # Create group key: source_ip + pattern detection
                pattern = self._detect_pattern(ml_input)
                group_key = f"{source_ip}_{pattern}_{severity}"
                
                grouped[group_key].append({
                    "source_ip": source_ip,
                    "severity": severity,
                    "probability": probability,
                    "timestamp": timestamp,
                    "ml_input": ml_input,
                    "agent_name": agent_name,
                    "pattern": pattern,
                    "message": alert.get("message", "")
                })
            except Exception as e:
                logger.warning(f"⚠ Error grouping alert: {str(e)}")
                continue
        
        # Convert to list and calculate group stats
        result = []
        for group_key, items in grouped.items():
            # Use the actual values from items instead of parsing group_key
            # since pattern names may contain underscores (e.g., "blocked_traffic")
            source_ip = items[0]["source_ip"]
            pattern = items[0]["pattern"]
            severity = items[0]["severity"]
            
            # Calculate average probability
            avg_probability = sum(item["probability"] for item in items) / len(items)
            
            result.append({
                "group_key": group_key,
                "source_ip": source_ip,
                "pattern": pattern,
                "severity": severity,
                "alert_count": len(items),
                "avg_probability": round(avg_probability, 3),
                "agents": list(set(item["agent_name"] for item in items)),
                "sample_alerts": items[:5]  # Keep first 5 for context
            })
        
        return sorted(result, key=lambda x: x["alert_count"], reverse=True)
    
    def _detect_pattern(self, ml_input: str) -> str:
        """Auto-detect attack pattern from ml_input"""
        ml_input_lower = ml_input.lower() if ml_input else ""
        
        # Check for pattern matches in order of priority
        for pattern_name, keywords in self.ATTACK_PATTERNS.items():
            for keyword in keywords:
                if keyword.lower() in ml_input_lower:
                    return pattern_name
        
        # Default pattern
        return "unknown"
    
    def _calculate_risk_score(self, grouped_alerts: List[Dict]) -> float:
        """
        Calculate risk score with improved formula:
        - Base score starts at 0.5 (not 0)
        - Logarithmic scaling for alert counts (avoid easy 100 score)
        - Weighted by severity distribution
        - Considers attack pattern escalation
        
        Formula:
        base_score = 0.5
        volume_score = log10(total_alerts + 1) * 15  # Logarithmic scaling
        severity_score = (ERROR% * 30) + (WARNING% * 15) + (INFO% * 5)
        confidence_score = avg_confidence * 25
        escalation_score = escalation_level * 15
        
        Final: base_score + volume + severity + confidence + escalation (max 100)
        """
        if not grouped_alerts:
            return 0.5  # Base score
        
        import math
        
        # Calculate total alerts and severity distribution
        total_alerts = sum(g["alert_count"] for g in grouped_alerts)
        error_count = sum(g["alert_count"] for g in grouped_alerts if g["severity"] == "ERROR")
        warning_count = sum(g["alert_count"] for g in grouped_alerts if g["severity"] == "WARNING")
        info_count = sum(g["alert_count"] for g in grouped_alerts if g["severity"] == "INFO")
        
        # 1. Base score (always starts at 0.5)
        base_score = 0.5
        
        # 2. Volume score (logarithmic to prevent easy 100)
        # log10(1) = 0, log10(10) = 1, log10(100) = 2, log10(1000) = 3
        volume_score = math.log10(total_alerts + 1) * 10  # Reduced from 15 to 10
        
        # 3. Severity distribution score (weighted percentages)
        error_pct = error_count / total_alerts if total_alerts > 0 else 0
        warning_pct = warning_count / total_alerts if total_alerts > 0 else 0
        info_pct = info_count / total_alerts if total_alerts > 0 else 0
        
        severity_score = (error_pct * 35) + (warning_pct * 15) + (info_pct * 3)  # Increased ERROR weight, reduced INFO
        
        # 4. Confidence score (average ML prediction probability)
        total_probability = sum(g["avg_probability"] * g["alert_count"] for g in grouped_alerts)
        avg_confidence = total_probability / total_alerts if total_alerts > 0 else 0
        confidence_score = avg_confidence * 30  # Increased from 25 to 30
        
        # 5. Escalation score (attack pattern sequences)
        escalation_level = self._detect_escalation(grouped_alerts)
        escalation_score = escalation_level * 20  # Increased from 15 to 20
        
        # Final score calculation
        final_score = base_score + volume_score + severity_score + confidence_score + escalation_score
        
        # Cap at 100
        return min(round(final_score, 1), 100.0)
    
    def _detect_escalation(self, grouped_alerts: List[Dict]) -> float:
        """
        Detect attack pattern escalation (sequence: reconnaissance → brute force → lateral movement)
        Returns: 0 (none), 1 (single pattern), 2 (sequence detected)
        """
        patterns_detected = set()
        
        for group in grouped_alerts:
            pattern = group.get("pattern", "unknown")
            if pattern != "unknown":
                patterns_detected.add(pattern)
        
        # Check for typical attack sequence
        attack_sequence = ["reconnaissance", "brute_force", "lateral_movement", "exfiltration"]
        matches = [p for p in attack_sequence if p in patterns_detected]
        
        if len(matches) >= 2:
            return 2.0  # Sequence detected
        elif matches:
            return 1.0  # Single pattern
        else:
            return 0.0  # No pattern
    
    def _generate_summary(self, grouped_alerts: List[Dict], risk_score: float, include_ai: bool = True) -> str:
        """
        Generate detailed summary of grouped alerts
        
        Args:
            grouped_alerts: Grouped alert data
            risk_score: Calculated risk score
            include_ai: Whether to include AI analysis (default: True)
        
        Returns:
            str: Formatted summary text
        """
        try:
            # Build context from grouped alerts
            alert_context = self._build_alert_context(grouped_alerts, risk_score)
            
            # Build detailed summary text
            summary = self._build_detailed_summary(alert_context, grouped_alerts, risk_score)
            
            return summary if summary else self._build_fallback_summary(grouped_alerts)
        
        except Exception as e:
            logger.error(f"❌ Summary generation failed: {str(e)}")
            return self._build_fallback_summary(grouped_alerts)
    
    def get_ai_analysis(self, grouped_alerts: List[Dict], risk_score: float) -> str:
        """
        Get AI analysis and recommendations using LLM + RAG
        
        Args:
            grouped_alerts: Grouped alert data
            risk_score: Calculated risk score
        
        Returns:
            str: AI-generated analysis and recommendations
        """
        try:
            # Extract patterns
            patterns = {}
            for group in grouped_alerts[:5]:
                pattern = group.get('pattern', 'unknown')
                if pattern not in patterns:
                    patterns[pattern] = {
                        'count': 0,
                        'severity': group.get('severity', 'INFO'),
                        'ips': set()
                    }
                patterns[pattern]['count'] += group.get('alert_count', 0)
                patterns[pattern]['ips'].add(group.get('source_ip', 'unknown'))
            
            # Build query
            pattern_summary = []
            for pattern, data in patterns.items():
                pattern_summary.append(
                    f"- {pattern.upper()}: {data['count']} alerts, {len(data['ips'])} IPs"
                )
            
            # Load prompt from file
            prompt_path = "prompts/instructions/alert_ai_analysis.json"
            system_prompt = ""
            user_template = ""
            
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_data = json.load(f)
                    system_prompt = prompt_data.get('system_prompt', '')
                    user_template = prompt_data.get('user_prompt_template', '')
            except Exception as e:
                logger.warning(f"⚠️  Failed to load prompt from {prompt_path}: {e}. Using fallback.")
                # Fallback prompt
                system_prompt = "Bạn là chuyên gia SOC Analyst. Phân tích cảnh báo và đưa ra khuyến nghị ngắn gọn."
                user_template = """Phân tích tóm tắt cảnh báo bảo mật này và đưa ra khuyến nghị ngắn gọn:

Risk Score: {risk_score}/100
Tổng số alerts: {total_alerts}

Các mẫu tấn công chính:
{attack_patterns}

Hãy cung cấp:
1. Đánh giá mức độ nguy hiểm (2-3 câu)
2. 3 hành động khuyến nghị ưu tiên (ngắn gọn, dạng bullet point)
3. MITRE ATT&CK techniques cần điều tra (nếu có)

Giữ phản hồi dưới 250 từ, cụ thể và có thể hành động."""
            
            # Build user query from template
            query = user_template.format(
                risk_score=f"{risk_score:.1f}",
                total_alerts=sum(g['alert_count'] for g in grouped_alerts),
                attack_patterns='\n'.join(pattern_summary)
            )
            
            # Prepend system prompt to query for LLM
            full_query = f"{system_prompt}\n\n{query}"
            
            # Call LLM with RAG
            response = self.llm_service.ask_rag(full_query)
            
            if response.get('status') == 'success':
                return response.get('answer', '')
            else:
                logger.warning(f"⚠️  AI analysis failed: {response.get('error', '')}")
                return ""
        
        except Exception as e:
            logger.error(f"❌ AI analysis error: {str(e)}")
            return ""
    
    def _build_detailed_summary(self, alert_context: str, grouped_alerts: List[Dict], risk_score: float) -> str:
        """Build detailed summary from grouped alerts"""
        summary = f"🚨 ML Alert Analysis\n\n"
        summary += f"Risk Assessment:\n"
        
        if risk_score >= 70:
            summary += f"⚠️ CRITICAL RISK ({risk_score:.1f}/100)\n"
            summary += "Immediate action required. Multiple attack patterns detected with high confidence.\n\n"
        elif risk_score >= 50:
            summary += f"🔴 HIGH RISK ({risk_score:.1f}/100)\n"
            summary += "Significant security concern. Review alerts and implement recommended actions.\n\n"
        elif risk_score >= 30:
            summary += f"🟡 MEDIUM RISK ({risk_score:.1f}/100)\n"
            summary += "Monitor closely. Take precautionary measures and investigate patterns.\n\n"
        else:
            summary += f"🟢 LOW RISK ({risk_score:.1f}/100)\n"
            summary += "Routine security monitoring. Continue standard procedures.\n\n"
        
        # Detected Patterns
        if grouped_alerts:
            summary += "Detected Attack Patterns:\n"
            patterns = {}
            
            for group in grouped_alerts:
                pattern = group['pattern']
                if pattern not in patterns:
                    patterns[pattern] = []
                patterns[pattern].append(group)
            
            pattern_descriptions = {
                "reconnaissance": "Information gathering to identify targets and vulnerabilities",
                "brute_force": "Credential attack attempts (login, password bruteforce)",
                "lateral_movement": "Movement within network to compromise additional systems",
                "exfiltration": "Data theft or unauthorized data transfer",
                "network_attack": "Network-level attacks (DDoS, flooding, amplification)",
                "malware": "Malware, trojan, virus, ransomware, or exploit detection",
                "web_attack": "Web application attacks (SQL injection, XSS, etc.)",
                "blocked_traffic": "Firewall blocked connections and denied traffic",
                "suspicious_traffic": "Suspicious or anomalous network activity",
                "unknown": "Unclassified security activity"
            }
            
            for pattern, groups in patterns.items():
                desc = pattern_descriptions.get(pattern, "Security event")
                total_alerts = sum(g['alert_count'] for g in groups)
                avg_prob = sum(g['avg_probability'] for g in groups) / len(groups)
                unique_ips = len(set(g['source_ip'] for g in groups))
                
                summary += f"\n  • {pattern.upper().replace('_', ' ')}\n"
                summary += f"    - Description: {desc}\n"
                summary += f"    - Total Alerts: {total_alerts}\n"
                summary += f"    - Avg Confidence: {avg_prob*100:.1f}%\n"
                summary += f"    - Affected IPs: {unique_ips}\n"
        
        # Top Affected Assets
        if grouped_alerts:
            summary += "\n\n<b>Top Affected Assets:</b>\n"
            top_ips = sorted(grouped_alerts, key=lambda x: x['alert_count'], reverse=True)[:3]
            
            for i, group in enumerate(top_ips, 1):
                summary += f"\n  {i}. <code>{group['source_ip']}</code>\n"
                summary += f"     - Alerts: {group['alert_count']}\n"
                summary += f"     - Pattern: {group['pattern'].upper()}\n"
                summary += f"     - Severity: {group['severity']}\n"
                summary += f"     - Probability: {group['avg_probability']:.1%}\n"
        
        # Recommended Actions
        summary += "\n\n<b>Recommended Actions:</b>\n"
        
        if risk_score >= 70:
            summary += "  1. 🚨 IMMEDIATE: Block or isolate affected source IPs\n"
            summary += "  2. 📋 Investigate active sessions from affected IPs\n"
            summary += "  3. 🔑 Review and reset credentials for compromised accounts\n"
            summary += "  4. 📊 Escalate to Security Operations Center (SOC)\n"
            summary += "  5. 📝 Document incident for forensic analysis\n"
        elif risk_score >= 50:
            summary += "  1. 🔍 Conduct in-depth analysis of alert patterns\n"
            summary += "  2. 🛡️ Enable enhanced monitoring for affected assets\n"
            summary += "  3. ⚠️ Prepare incident response procedures\n"
            summary += "  4. 📞 Alert security team for investigation\n"
        elif risk_score >= 30:
            summary += "  1. 📊 Monitor trends and pattern changes\n"
            summary += "  2. 🔍 Investigate high-confidence alerts\n"
            summary += "  3. 🛡️ Review firewall and access control rules\n"
            summary += "  4. 📈 Update threat intelligence\n"
        else:
            summary += "  1. ✅ Continue routine monitoring\n"
            summary += "  2. 📋 Archive alerts for audit trail\n"
            summary += "  3. 🔄 Review and update detection rules\n"
        
        return summary
    
    def _build_alert_context(self, grouped_alerts: List[Dict], risk_score: float) -> str:
        """Build context string from grouped alerts"""
        context = "ML Alert Summary Context:\n\n"
        
        for i, group in enumerate(grouped_alerts[:5], 1):  # Top 5 groups
            context += f"Group {i}:\n"
            context += f"  Source IP: {group['source_ip']}\n"
            context += f"  Pattern: {group['pattern']}\n"
            context += f"  Severity: {group['severity']}\n"
            context += f"  Alert Count: {group['alert_count']}\n"
            context += f"  Avg ML Probability: {group['avg_probability']}\n"
            context += f"  Agents: {', '.join(group['agents'])}\n"
            context += f"  Sample: {group['sample_alerts'][0]['ml_input'][:100]}...\n\n"
        
        context += f"Overall Risk Score: {risk_score}/100\n"
        
        return context
    
    def _build_fallback_summary(self, grouped_alerts: List[Dict]) -> str:
        """Build a fallback summary if generation fails"""
        if not grouped_alerts:
            return "No alerts to summarize."
        
        total_alerts = sum(g["alert_count"] for g in grouped_alerts)
        high_severity = sum(1 for g in grouped_alerts if g["severity"] == "ERROR")
        
        summary = f"Alert Summary: {total_alerts} total alerts detected. "
        summary += f"{high_severity} with ERROR severity. "
        
        top_patterns = list(set(g["pattern"] for g in grouped_alerts[:3]))
        if top_patterns and top_patterns[0] != "unknown":
            summary += f"Detected patterns: {', '.join(top_patterns)}. "
        
        summary += "Review individual alert groups for detailed analysis."
        
        return summary


def get_alert_summarization_service() -> AlertSummarizationService:
    """Get singleton instance of Alert Summarization Service"""
    return AlertSummarizationService()
