"""
LLM Service - AI Analysis cho IntelOwl results
"""
import os
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
from app.config import CHAT_MODEL, OPENAI_TIMEOUT, OPENAI_MAX_RETRIES

# Import analyzer registry
from app.services.analyzers import get_handler, get_all_handlers, get_registered_analyzer_names

load_dotenv()

# Project root for prompt files
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


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
        self.prompts_dir = PROJECT_ROOT / "prompts"
    
    def _load_prompt_config(self, prompt_file: str) -> dict:
        """
        Load prompt configuration từ file JSON
        
        Args:
            prompt_file: Tên file prompt (relative to prompts directory)
        
        Returns:
            dict: Prompt configuration
        """
        prompt_path = self.prompts_dir / prompt_file
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
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
        # Load prompt configuration
        try:
            prompt_config = self._load_prompt_config("instructions/ioc_enrichment.json")
        except FileNotFoundError as e:
            print(f"[ERROR LLM] {str(e)}")
            return {
                "summary": f"Lỗi: Không tìm thấy file prompt config",
                "risk_level": "UNKNOWN",
                "key_findings": [],
                "recommendations": []
            }
        
        # Extract key info
        analyzer_reports = raw_results.get('analyzer_reports', [])
        connector_reports = raw_results.get('connector_reports', [])
        
        # **OPTIMIZATION 1: Chỉ lấy SUCCESS analyzers**
        successful_analyzers = [
            a for a in analyzer_reports 
            if a.get('status') == 'SUCCESS'
        ]
        
        # Get settings from config
        settings = prompt_config.get('settings', {})
        max_analyzers = settings.get('max_analyzers_to_include', 15)
        max_tokens = settings.get('max_completion_tokens', 1500)
        
        # **OPTIMIZATION 2: Pre-compute statistics (giảm công việc cho LLM)**
        stats = self._compute_threat_stats(successful_analyzers)
        
        # **OPTIMIZATION 3: Extract ONLY critical findings, không gửi raw report**
        critical_findings = self._extract_critical_findings(successful_analyzers, max_analyzers)
        
        # Count stats
        total_analyzers = len(analyzer_reports)
        successful_count = len(successful_analyzers)
        
        print(f"[DEBUG LLM] Total: {total_analyzers}, Success: {successful_count}, Critical findings: {len(critical_findings)}")
        print(f"[DEBUG LLM] Pre-computed stats: {stats}")
        
        # Build prompt from template
        user_prompt_template = prompt_config.get('user_prompt_template', '')
        system_prompt = prompt_config.get('system_prompt', 'You are a cybersecurity expert.')
        
        prompt = user_prompt_template.format(
            ioc_value=ioc_value,
            total_analyzers=total_analyzers,
            successful_count=successful_count,
            connector_count=len(connector_reports),
            analyzer_findings=json.dumps(critical_findings, indent=2, ensure_ascii=False),
            threat_stats=json.dumps(stats, indent=2, ensure_ascii=False)
        )
        
        # Call OpenAI
        try:
            response = self.openai_client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_completion_tokens=max_tokens
            )
            
            ai_text = response.choices[0].message.content or ""
            
            # Determine risk level from original reports
            risk_level = self._determine_risk_level(analyzer_reports)
            
            # Extract recommendations
            recommendations = self._extract_recommendations(ai_text)
            
            return {
                "summary": ai_text,
                "risk_level": risk_level,
                "key_findings": self._extract_key_findings(successful_analyzers),
                "recommendations": recommendations
            }
            
        except Exception as e:
            print(f"[ERROR LLM] {str(e)}")
            return {
                "summary": f"Lỗi khi phân tích: {str(e)}",
                "risk_level": "UNKNOWN",
                "key_findings": [],
                "recommendations": []
            }
    
    def _determine_risk_level(self, analyzer_reports: list) -> str:
        """
        Tính risk level dựa trên tất cả registered analyzers.
        Sử dụng registry pattern - tự động support analyzer mới.
        """
        max_risk_score = 0
        
        for report in analyzer_reports:
            if report.get('status') != 'SUCCESS':
                continue
            
            name = report.get('name', '')
            report_data = report.get('report', {})
            
            # Tìm handler cho analyzer này
            handler = get_handler(name)
            if handler:
                risk_score = handler.get_risk_score(report_data)
                max_risk_score = max(max_risk_score, risk_score)
        
        # Convert score to level
        if max_risk_score >= 80:
            return "CRITICAL"
        elif max_risk_score >= 60:
            return "HIGH"
        elif max_risk_score >= 30:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _compute_threat_stats(self, analyzer_reports: list) -> dict:
        """
        Pre-compute threat statistics từ tất cả registered analyzers.
        Sử dụng registry pattern - tự động support analyzer mới.
        
        Returns:
            dict với các stats đã tính sẵn
        """
        stats = {
            "total_analyzed": len(analyzer_reports),
            "registered_analyzers": get_registered_analyzer_names(),
            "analyzer_stats": {},
            "max_risk_score": 0,
            "malicious_count": 0
        }
        
        for analyzer in analyzer_reports:
            name = analyzer.get('name', '')
            report = analyzer.get('report', {})
            
            # Tìm handler cho analyzer này
            handler = get_handler(name)
            if handler:
                # Extract stats using handler
                analyzer_stats = handler.extract_stats(report)
                stats["analyzer_stats"][handler.display_name] = analyzer_stats
                
                # Update risk score
                risk_score = handler.get_risk_score(report)
                stats["max_risk_score"] = max(stats["max_risk_score"], risk_score)
                
                # Count malicious
                if handler.is_malicious(report):
                    stats["malicious_count"] += 1
        
        return stats
    
    def _extract_critical_findings(self, analyzer_reports: list, max_findings: int = 10) -> list:
        """
        Extract findings từ tất cả registered analyzers.
        Sử dụng registry pattern - tự động support analyzer mới.
        Sort theo priority của handler.
        """
        findings = []
        
        # Collect findings with priority
        findings_with_priority = []
        
        for analyzer in analyzer_reports:
            name = analyzer.get('name', '')
            
            # Tìm handler cho analyzer này
            handler = get_handler(name)
            if handler:
                summary = handler.summarize(analyzer)
                if summary:
                    findings_with_priority.append({
                        "priority": handler.priority,
                        "finding": summary
                    })
        
        # Sort by priority (cao hơn = quan trọng hơn)
        findings_with_priority.sort(key=lambda x: x["priority"], reverse=True)
        
        # Extract top findings
        findings = [f["finding"] for f in findings_with_priority[:max_findings]]
        
        return findings
    
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
