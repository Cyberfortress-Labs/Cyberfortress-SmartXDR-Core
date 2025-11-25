"""
LLM Service - AI Analysis cho IntelOwl results
"""
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from app.config import CHAT_MODEL, OPENAI_TIMEOUT, OPENAI_MAX_RETRIES

load_dotenv()


class LLMService:
    """
    Service để gọi LLM APIs cho AI analysis
    """
    
    def __init__(self):
        self.openai_client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            timeout=OPENAI_TIMEOUT,
            max_retries=OPENAI_MAX_RETRIES
        )
        self.chat_model = CHAT_MODEL
    
    def explain_intelowl_results(self, ioc_value: str, raw_results: dict) -> dict:
        """
        Dùng AI giải thích IntelOwl raw JSON results
        
        Args:
            ioc_value: Giá trị IOC (IP/domain/hash/url)
            raw_results: Raw JSON từ IntelOwl
        
        Returns:
            {
                "summary": "Tóm tắt bằng tiếng Việt...",
                "risk_level": "CRITICAL/HIGH/MEDIUM/LOW",
                "key_findings": [...],
                "recommendations": [...]
            }
        """
        # Extract key info
        analyzer_reports = raw_results.get('analyzer_reports', [])
        connector_reports = raw_results.get('connector_reports', [])
        
        # Count successful analyzers
        total_analyzers = len(analyzer_reports)
        successful = sum(1 for a in analyzer_reports if a.get('status') == 'SUCCESS')
        
        # Build prompt
        prompt = f"""
Bạn là chuyên gia phân tích mã độc (Malware Analyst). Hãy phân tích kết quả IntelOwl sau:

**IOC:** {ioc_value}

**TỔNG QUAN:**
- Tổng số analyzers: {total_analyzers}
- Thành công: {successful}
- Connector reports: {len(connector_reports)}

**RAW ANALYZER REPORTS (top 5):**
{json.dumps(analyzer_reports[:5], indent=2, ensure_ascii=False)}

**YÊU CẦU PHÂN TÍCH:**

1. **Tóm tắt (3-5 câu):**
   - IOC này có độc hại không? Mức độ nguy hiểm?
   
2. **Các phát hiện quan trọng (3-5 điểm):**
   - Liệt kê findings quan trọng nhất từ analyzers
   
3. **Hành động đề xuất (2-3 điểm):**
   - Block/Quarantine/Monitor/Investigate?
   - Các bước cụ thể

**FORMAT:** Markdown, tiếng Việt, chuyên nghiệp nhưng dễ hiểu.
"""

        # Call OpenAI
        try:
            response = self.openai_client.responses.create(
                model=self.chat_model,
                instructions="You are a cybersecurity expert explaining threat intelligence data clearly in Vietnamese.",
                input=prompt
            )
            
            ai_text = response.output_text
            
            # Determine risk level
            risk_level = self._determine_risk_level(analyzer_reports)
            
            # Extract recommendations
            recommendations = self._extract_recommendations(ai_text)
            
            return {
                "summary": ai_text,
                "risk_level": risk_level,
                "key_findings": self._extract_key_findings(analyzer_reports),
                "recommendations": recommendations
            }
            
        except Exception as e:
            return {
                "summary": f"Lỗi khi phân tích: {str(e)}",
                "risk_level": "UNKNOWN",
                "key_findings": [],
                "recommendations": []
            }
    
    def _determine_risk_level(self, analyzer_reports: list) -> str:
        """
        Tính risk level dựa trên analyzer reports
        """
        malicious_count = 0
        
        for report in analyzer_reports:
            if report.get('status') != 'SUCCESS':
                continue
                
            report_data = report.get('report', {})
            
            # Check VirusTotal
            if 'VirusTotal' in report.get('name', ''):
                positives = report_data.get('positives', 0)
                malicious_count += positives
            
            # Check other malicious indicators
            if 'malicious' in str(report_data).lower():
                malicious_count += 1
        
        if malicious_count > 10:
            return "CRITICAL"
        elif malicious_count > 5:
            return "HIGH"
        elif malicious_count > 0:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _extract_key_findings(self, analyzer_reports: list) -> list:
        """
        Extract key findings từ analyzer reports
        """
        findings = []
        
        for report in analyzer_reports[:5]:  # Top 5
            if report.get('status') == 'SUCCESS':
                findings.append({
                    "analyzer": report.get('name'),
                    "status": report.get('status')
                })
        
        return findings
    
    def _extract_recommendations(self, ai_text: str) -> list:
        """
        Extract recommendations từ AI response
        """
        # Simple extraction - tìm các dòng bắt đầu bằng - hoặc số
        lines = ai_text.split('\n')
        recommendations = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('•') or (line and line[0].isdigit() and '.' in line):
                recommendations.append(line.lstrip('-•0123456789. '))
        
        return recommendations[:5]  # Top 5
