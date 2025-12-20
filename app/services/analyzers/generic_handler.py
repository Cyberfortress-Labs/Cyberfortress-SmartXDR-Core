"""
Generic Analyzer Handler

Fallback handler cho các analyzers không có handler riêng.
Xử lý chung chung để hệ thống vẫn hoạt động thay vì báo lỗi.
"""
from . import BaseAnalyzerHandler, register_analyzer


@register_analyzer('generic')
class GenericHandler(BaseAnalyzerHandler):
    """
    Generic handler cho các analyzers không có handler riêng.
    Dùng làm fallback để xử lý bất kỳ analyzer nào.
    """
    
    display_name = "Generic Analyzer"
    priority = 10  # Low priority - chỉ dùng khi không có handler khác
    
    def extract_stats(self, report: dict) -> dict:
        """
        Extract basic stats từ report một cách generic.
        Tự động detect các field phổ biến.
        """
        if not report:
            return {"found": False}
        
        # Handle string reports
        if isinstance(report, str):
            return {
                "found": bool(report.strip()),
                "type": "string",
                "length": len(report)
            }
        
        # Handle list reports
        if isinstance(report, list):
            return {
                "found": len(report) > 0,
                "type": "list",
                "count": len(report)
            }
        
        # Handle dict reports - extract common patterns
        stats = {"found": True, "type": "dict"}
        
        # Common field patterns found in many analyzers
        common_fields = {
            # Detection/verdict fields
            "malicious": ["malicious", "is_malicious", "isMalicious"],
            "score": ["score", "risk_score", "threat_score", "confidence", "abuseConfidenceScore"],
            "verdict": ["verdict", "result", "status", "classification"],
            "detected": ["detected", "positive", "positives", "detections"],
            
            # Count fields
            "total": ["total", "count", "total_reports", "totalReports"],
            
            # Threat intel fields
            "threat_level": ["threat_level", "threat_level_id", "severity"],
            "category": ["category", "type", "threat_type"],
            
            # Results
            "data": ["data", "results", "response", "report"]
        }
        
        for stat_name, field_options in common_fields.items():
            for field in field_options:
                if field in report:
                    value = report[field]
                    # Convert to serializable format
                    if isinstance(value, (str, int, float, bool)):
                        stats[stat_name] = value
                    elif isinstance(value, list):
                        stats[stat_name] = len(value)
                    elif isinstance(value, dict):
                        stats[stat_name] = len(value)
                    break
        
        # Estimate if report contains useful data
        stats["has_data"] = len(report) > 0
        stats["field_count"] = len(report)
        
        return stats
    
    def summarize(self, analyzer: dict) -> dict:
        """
        Tóm tắt report một cách generic (~50-100 tokens).
        """
        name = analyzer.get('name', 'Unknown Analyzer')
        report = analyzer.get('report', {})
        status = analyzer.get('status', 'UNKNOWN')
        
        summary = {
            "analyzer": name,
            "type": "generic",
            "status": status
        }
        
        if not report:
            summary["found"] = False
            summary["verdict"] = "unknown"
            return summary
        
        # Handle string reports
        if isinstance(report, str):
            summary["found"] = bool(report.strip())
            summary["verdict"] = "unknown"
            summary["note"] = f"String response ({len(report)} chars)"
            return summary
        
        # Handle list reports
        if isinstance(report, list):
            summary["found"] = len(report) > 0
            summary["verdict"] = "suspicious" if len(report) > 0 else "unknown"
            summary["result_count"] = len(report)
            return summary
        
        # Handle dict reports
        stats = self.extract_stats(report)
        summary["found"] = stats.get("has_data", False)
        
        # Determine verdict based on common patterns
        verdict = "unknown"
        
        if stats.get("malicious"):
            verdict = "malicious"
        elif stats.get("detected"):
            detected = stats["detected"]
            if isinstance(detected, int) and detected > 0:
                verdict = "malicious"
            elif detected is True:
                verdict = "malicious"
        elif stats.get("score"):
            score = stats["score"]
            if isinstance(score, (int, float)):
                if score > 70:
                    verdict = "malicious"
                elif score > 40:
                    verdict = "suspicious"
                else:
                    verdict = "clean"
        elif stats.get("verdict"):
            raw_verdict = str(stats["verdict"]).lower()
            if any(m in raw_verdict for m in ["malicious", "bad", "danger", "high"]):
                verdict = "malicious"
            elif any(s in raw_verdict for s in ["suspicious", "medium", "warning"]):
                verdict = "suspicious"
            elif any(c in raw_verdict for c in ["clean", "safe", "good", "low"]):
                verdict = "clean"
        
        summary["verdict"] = verdict
        
        # Add key stats to summary
        for key in ["score", "detected", "total", "threat_level", "category"]:
            if key in stats:
                summary[key] = stats[key]
        
        return summary
    
    def get_risk_score(self, report: dict) -> int:
        """
        Tính risk score generic (0-100).
        Cố gắng extract từ các field phổ biến.
        """
        if not report:
            return 0
        
        # Handle string reports
        if isinstance(report, str):
            # If contains certain keywords, assign moderate risk
            lower_report = report.lower()
            if any(w in lower_report for w in ["malicious", "threat", "attack", "exploit"]):
                return 60
            elif any(w in lower_report for w in ["suspicious", "warning", "risk"]):
                return 40
            return 20 if report.strip() else 0
        
        # Handle list reports
        if isinstance(report, list):
            # More results = potentially more risk
            count = len(report)
            if count > 10:
                return 70
            elif count > 5:
                return 50
            elif count > 0:
                return 30
            return 0
        
        # Handle dict reports
        score = 0
        
        # Direct score fields
        score_fields = ["score", "risk_score", "threat_score", "confidence", "abuseConfidenceScore"]
        for field in score_fields:
            if field in report:
                value = report[field]
                if isinstance(value, (int, float)):
                    if 0 <= value <= 100:
                        score = max(score, int(value))
                    elif 0 <= value <= 1:  # Normalized score
                        score = max(score, int(value * 100))
                break
        
        # Detection counts
        if "positives" in report or "detected" in report:
            detected = report.get("positives", report.get("detected", 0))
            if isinstance(detected, int) and detected > 0:
                total = report.get("total", detected)
                ratio = detected / total if total > 0 else 0
                detection_score = min(100, int(ratio * 100) + 20)
                score = max(score, detection_score)
        
        # Boolean malicious flags
        malicious_fields = ["malicious", "is_malicious", "isMalicious", "is_bad"]
        for field in malicious_fields:
            if report.get(field) is True:
                score = max(score, 80)
                break
        
        # Threat level (1=high, 4=low typically)
        if "threat_level_id" in report:
            tl = report["threat_level_id"]
            if isinstance(tl, (int, str)):
                try:
                    tl_int = int(tl)
                    if tl_int == 1:
                        score = max(score, 90)
                    elif tl_int == 2:
                        score = max(score, 70)
                    elif tl_int == 3:
                        score = max(score, 50)
                except ValueError:
                    pass
        
        # If we found data but couldn't determine score, assign baseline
        if score == 0 and len(report) > 0:
            score = 25  # Baseline for having some data
        
        return min(100, score)
    
    def is_malicious(self, report: dict) -> bool:
        """
        Quick check xem report có malicious không.
        """
        return self.get_risk_score(report) >= 60
