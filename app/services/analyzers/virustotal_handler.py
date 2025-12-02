"""
VirusTotal Analyzer Handler
"""
from . import BaseAnalyzerHandler, register_analyzer


@register_analyzer('virustotal')
class VirusTotalHandler(BaseAnalyzerHandler):
    """
    Handler cho VirusTotal analyzer.
    Supports cả VT API v2 và v3 formats.
    """
    
    display_name = "VirusTotal"
    priority = 100  # Highest priority
    
    def extract_stats(self, report: dict) -> dict:
        """
        Extract key stats từ VirusTotal report.
        """
        if not report:
            return {"error": "Empty report"}
        
        # Handle case when report is a string (error message or raw response)
        if isinstance(report, str):
            return {"error": f"Invalid report format: {report[:100]}"}
        
        # VT v3 API format
        if 'data' in report:
            attributes = report.get('data', {}).get('attributes', {})
            last_analysis = attributes.get('last_analysis_stats', {})
            
            return {
                "malicious": last_analysis.get('malicious', 0),
                "suspicious": last_analysis.get('suspicious', 0),
                "harmless": last_analysis.get('harmless', 0),
                "undetected": last_analysis.get('undetected', 0),
                "reputation": attributes.get('reputation', 0),
                "tags": attributes.get('tags', [])[:5],
                "country": attributes.get('country', ''),
                "api_version": "v3"
            }
        
        # VT v2 API format
        return {
            "malicious": report.get('positives', 0),
            "total": report.get('total', 0),
            "scan_date": report.get('scan_date', ''),
            "api_version": "v2"
        }
    
    def summarize(self, analyzer: dict) -> dict:
        """
        Tóm tắt VirusTotal report (~50-100 tokens).
        """
        name = analyzer.get('name', 'VirusTotal')
        report = analyzer.get('report', {})
        
        if not report:
            return None
        
        # Handle case when report is a string
        if isinstance(report, str):
            return None
        
        summary: dict = {
            "analyzer": name,
            "type": "virustotal"
        }
        
        # VT v3 API format
        if 'data' in report:
            attributes = report.get('data', {}).get('attributes', {})
            last_analysis = attributes.get('last_analysis_stats', {})
            
            malicious = last_analysis.get('malicious', 0)
            suspicious = last_analysis.get('suspicious', 0)
            total = sum(last_analysis.values()) if last_analysis else 0
            
            summary["verdict"] = "malicious" if malicious > 0 else ("suspicious" if suspicious > 0 else "clean")
            summary["score"] = f"{malicious}/{total} engines detected"
            summary["reputation"] = attributes.get('reputation', 0)
            
            # Top detected threats
            last_analysis_results = attributes.get('last_analysis_results', {})
            detected = []
            for engine, result in last_analysis_results.items():
                if result.get('category') == 'malicious':
                    detected.append({
                        "engine": engine,
                        "result": result.get('result', '')
                    })
            summary["detections"] = detected[:5]  # Top 5
            
        # VT v2 API format
        else:
            positives = report.get('positives', 0)
            total = report.get('total', 0)
            summary["verdict"] = "malicious" if positives > 0 else "clean"
            summary["score"] = f"{positives}/{total} detections"
        
        return summary
    
    def get_risk_score(self, report: dict) -> int:
        """
        Tính risk score từ VT (0-100).
        
        Logic:
        - 0 detections = 0
        - 1-5 detections = 30-60
        - 6-10 detections = 60-80
        - >10 detections = 80-100
        """
        if not report:
            return 0
        
        # Handle case when report is a string
        if isinstance(report, str):
            return 0
        
        # VT v3
        if 'data' in report:
            stats = report.get('data', {}).get('attributes', {}).get('last_analysis_stats', {})
            malicious = stats.get('malicious', 0)
            suspicious = stats.get('suspicious', 0)
        else:
            # VT v2
            malicious = report.get('positives', 0)
            suspicious = 0
        
        total_bad = malicious + suspicious
        
        if total_bad == 0:
            return 0
        elif total_bad <= 5:
            return 30 + (total_bad * 6)  # 36-60
        elif total_bad <= 10:
            return 60 + ((total_bad - 5) * 4)  # 64-80
        else:
            return min(100, 80 + (total_bad - 10) * 2)  # 82-100
