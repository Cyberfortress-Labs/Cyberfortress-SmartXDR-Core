"""
Template Analyzer Handler

Copy file này và customize để thêm analyzer mới.

Các bước:
1. Copy file này thành <analyzer_name>_handler.py
2. Đổi tên class và decorator
3. Implement 3 methods: extract_stats, summarize, get_risk_score
4. Import trong __init__.py

Example cho Shodan:
    @register_analyzer('shodan')
    class ShodanHandler(BaseAnalyzerHandler):
        display_name = "Shodan"
        priority = 70
        ...
"""
from . import BaseAnalyzerHandler, register_analyzer


# Uncomment và customize cho analyzer mới
# @register_analyzer('analyzer_name')  # Thay 'analyzer_name' bằng tên thực
# class TemplateHandler(BaseAnalyzerHandler):
#     """
#     Handler cho [Analyzer Name].
#     """
#     
#     display_name = "Analyzer Name"  # Tên hiển thị
#     priority = 50  # 0-100, cao = quan trọng hơn
#     
#     def extract_stats(self, report: dict) -> dict:
#         """
#         Extract key statistics từ report.
#         Keep minimal - chỉ những gì cần để tính risk.
#         """
#         if not report:
#             return {}
#         
#         return {
#             "key_stat_1": report.get('field_1'),
#             "key_stat_2": report.get('field_2'),
#         }
#     
#     def summarize(self, analyzer: dict) -> dict:
#         """
#         Tóm tắt report (~50-100 tokens cho LLM).
#         """
#         name = analyzer.get('name', self.display_name)
#         report = analyzer.get('report', {})
#         
#         return {
#             "analyzer": name,
#             "type": "analyzer_type",
#             "verdict": "clean",  # clean/suspicious/malicious
#             "key_info": "summary here"
#         }
#     
#     def get_risk_score(self, report: dict) -> int:
#         """
#         Tính risk score (0-100).
#         0 = clean, 100 = critical
#         """
#         if not report:
#             return 0
#         
#         # Custom logic here
#         return 0


# ============================================================
# EXAMPLES: Các analyzer phổ biến (uncomment nếu cần)
# ============================================================

# @register_analyzer('shodan')
# class ShodanHandler(BaseAnalyzerHandler):
#     display_name = "Shodan"
#     priority = 70
#     
#     def extract_stats(self, report: dict) -> dict:
#         return {
#             "ports": report.get('ports', []),
#             "org": report.get('org', ''),
#             "vulns": report.get('vulns', [])
#         }
#     
#     def summarize(self, analyzer: dict) -> dict:
#         report = analyzer.get('report', {})
#         ports = report.get('ports', [])
#         vulns = report.get('vulns', [])
#         
#         verdict = "suspicious" if len(ports) > 10 or vulns else "clean"
#         
#         return {
#             "analyzer": "Shodan",
#             "type": "shodan",
#             "verdict": verdict,
#             "open_ports": len(ports),
#             "vulnerabilities": len(vulns),
#             "org": report.get('org', 'Unknown')
#         }
#     
#     def get_risk_score(self, report: dict) -> int:
#         if not report:
#             return 0
#         
#         score = 0
#         vulns = report.get('vulns', [])
#         ports = report.get('ports', [])
#         
#         # Vulns = high risk
#         score += len(vulns) * 20
#         
#         # Many open ports = medium risk
#         if len(ports) > 20:
#             score += 30
#         elif len(ports) > 10:
#             score += 15
#         
#         return min(100, score)


# @register_analyzer('abuseipdb')
# class AbuseIPDBHandler(BaseAnalyzerHandler):
#     display_name = "AbuseIPDB"
#     priority = 85
#     
#     def extract_stats(self, report: dict) -> dict:
#         return {
#             "confidence_score": report.get('abuseConfidenceScore', 0),
#             "total_reports": report.get('totalReports', 0),
#             "country": report.get('countryCode', ''),
#             "isp": report.get('isp', '')
#         }
#     
#     def summarize(self, analyzer: dict) -> dict:
#         report = analyzer.get('report', {})
#         score = report.get('abuseConfidenceScore', 0)
#         
#         if score > 80:
#             verdict = "malicious"
#         elif score > 50:
#             verdict = "suspicious"
#         else:
#             verdict = "clean"
#         
#         return {
#             "analyzer": "AbuseIPDB",
#             "type": "abuseipdb",
#             "verdict": verdict,
#             "confidence": f"{score}%",
#             "reports": report.get('totalReports', 0)
#         }
#     
#     def get_risk_score(self, report: dict) -> int:
#         return report.get('abuseConfidenceScore', 0)
