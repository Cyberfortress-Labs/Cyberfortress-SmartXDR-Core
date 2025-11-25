"""
LLM Service - AI Analysis for RAG queries and IntelOwl results
"""
import os
import re
import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any
from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from dotenv import load_dotenv
from app.config import (
    CHAT_MODEL, 
    DEFAULT_RESULTS,
    INPUT_PRICE_PER_1M, 
    OUTPUT_PRICE_PER_1M,
    OPENAI_TIMEOUT, 
    OPENAI_MAX_RETRIES,
    MAX_CALLS_PER_MINUTE,
    MAX_DAILY_COST,
    CACHE_ENABLED,
    CACHE_TTL,
    DEBUG_MODE,
    DEBUG_LLM,
    DEBUG_ANONYMIZATION
)

# Import analyzer registry
from app.services.analyzers import get_handler, get_all_handlers, get_registered_analyzer_names

load_dotenv()

# Project root for prompt files
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class LLMService:
    """
    Service để gọi LLM APIs cho AI analysis
    Bao gồm: RAG queries, IntelOwl analysis, etc.
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern để reuse connections"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.openai_client = OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            timeout=OPENAI_TIMEOUT,
            max_retries=OPENAI_MAX_RETRIES
        )
        self.chat_model = CHAT_MODEL
        self.prompts_dir = PROJECT_ROOT / "prompts"
        
        # Initialize utilities
        from app.utils.rate_limit import APIUsageTracker
        from app.utils.cache import ResponseCache
        from app.core.anonymizer import DataAnonymizer
        from app.services.prompt_builder_service import PromptBuilder
        
        self.usage_tracker = APIUsageTracker(
            max_calls_per_minute=MAX_CALLS_PER_MINUTE,
            max_daily_cost=MAX_DAILY_COST
        )
        self.response_cache = ResponseCache(ttl=CACHE_TTL, enabled=CACHE_ENABLED)
        self.anonymizer = DataAnonymizer()
        self.prompt_builder = PromptBuilder(prompt_file='rag_system.json')
        
        self._initialized = True
    
    # ==================== RAG Query Methods ====================
    
    def ask_rag(
        self, 
        collection, 
        query: str, 
        n_results: int = DEFAULT_RESULTS, 
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        RAG Query - Search and answer questions using ChromaDB context
        
        Args:
            collection: ChromaDB collection instance
            query: User's question
            n_results: Number of documents to retrieve
            filter_metadata: Optional metadata filter
        
        Returns:
            {
                "status": "success" | "error",
                "answer": "...",
                "cached": bool,
                "sources": [...],
                "error": "..." (if error)
            }
        """
        if DEBUG_MODE:
            print(f"\n[LLM Service] Question: {query}")
        
        # Check rate limit
        if not self.usage_tracker.check_rate_limit():
            return {
                "status": "error",
                "error": "Rate limit exceeded. Please wait a moment before trying again.",
                "error_type": "rate_limit"
            }
        
        # Search and build context
        context_text, sources, _ = self._search_and_build_context(
            collection, query, n_results, filter_metadata
        )
        
        # Check cache
        context_hash = hashlib.sha256(context_text.encode()).hexdigest()
        cache_key = self.response_cache.get_cache_key(query, context_hash)
        cached_response = self.response_cache.get(cache_key)
        
        if cached_response:
            return {
                "status": "success",
                "answer": cached_response,
                "cached": True,
                "sources": list(sources)
            }
        
        # Anonymize context
        context_text_anonymized = self._anonymize_context(context_text)
        
        # Build API request
        system_instructions = self.prompt_builder.build_rag_prompt()
        user_input = self._build_rag_user_input(context_text_anonymized, query)
        
        # Call API
        try:
            answer_with_tokens, actual_cost = self._call_responses_api(
                system_instructions, 
                user_input
            )
            
            # De-anonymize response
            answer = self._deanonymize_text(answer_with_tokens)
            
            # Add source citations
            if sources:
                answer += f"\n\nSources: {', '.join(sorted(sources))}"
            
            # Cache the response
            self.response_cache.set(cache_key, answer)
            
            return {
                "status": "success",
                "answer": answer,
                "cached": False,
                "sources": list(sources),
                "cost": actual_cost
            }
            
        except RateLimitError as e:
            return {
                "status": "error",
                "error": f"OpenAI rate limit exceeded. Please try again later.",
                "error_type": "rate_limit",
                "request_id": getattr(e, 'request_id', None)
            }
            
        except APIConnectionError as e:
            return {
                "status": "error",
                "error": f"Connection error: {str(e)}",
                "error_type": "connection"
            }
            
        except APIError as e:
            return {
                "status": "error",
                "error": f"OpenAI API error: {str(e)}",
                "error_type": "api_error",
                "request_id": getattr(e, 'request_id', None)
            }
    
    def _search_and_build_context(
        self, 
        collection, 
        query: str, 
        n_results: int, 
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """Search collection and build context from results"""
        effective_n_results = max(n_results, 5)
        
        search_params = {
            "query_texts": [query],
            "n_results": effective_n_results
        }
        
        if filter_metadata:
            search_params["where"] = filter_metadata
        
        results = collection.query(**search_params)
        
        # Check relevance
        has_relevant_results = False
        
        if results["documents"] and results["documents"][0]:
            if results["distances"] and results["distances"][0]:
                min_distance = min(results["distances"][0])
                has_relevant_results = min_distance < 1.4
            else:
                has_relevant_results = True
        
        if not has_relevant_results:
            return "No specific Cyberfortress documentation found for this query.", set(), []
        
        # Build context from results
        context_list = results["documents"][0]
        metadatas_list = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []
        
        context_parts = []
        sources = set()
        
        for idx, (doc, meta, dist) in enumerate(zip(context_list, metadatas_list, distances)):
            if dist < 1.4:
                context_parts.append(f"[Document {idx + 1}]\n{doc}")
                if meta and "source" in meta:
                    sources.add(meta["source"])
        
        context_text = "\n\n---\n\n".join(context_parts) if context_parts else "Limited relevant context found."
        
        return context_text, sources, context_list
    
    def _anonymize_context(self, text: str) -> str:
        """Anonymize sensitive information in text"""
        # Anonymize IP addresses
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        text = re.sub(ip_pattern, lambda m: self.anonymizer.anonymize_ip(m.group(), method='token'), text)
        
        # Anonymize device IDs
        device_pattern = r'\b([a-z]+-(?:[a-z]+-)?\d+)\b'
        text = re.sub(device_pattern, lambda m: self.anonymizer.anonymize_hostname(m.group(1), method='token'), text)
        
        return text
    
    def _deanonymize_text(self, text: str) -> str:
        """De-anonymize text by replacing tokens with original values"""
        token_pattern = r'(TKN-IP-[a-f0-9]+|HOST-[a-f0-9]+|USER-[a-f0-9]+|MAC-[a-f0-9]+)'
        
        def replace_token(match):
            token = match.group(1)
            original = self.anonymizer.deanonymize(token)
            return original if original else token
        
        return re.sub(token_pattern, replace_token, text)
    
    def _build_rag_user_input(self, context: str, query: str) -> str:
        """Build user input for RAG query"""
        user_prompt_template = self.prompt_builder.build_user_input_prompt()
        return user_prompt_template.format(context=context, query=query)
    
    def _call_responses_api(self, system_instructions: str, user_input: str) -> tuple:
        """
        Call OpenAI Responses API (for RAG queries)
        
        Returns:
            Tuple of (answer_text, actual_cost)
        """
        response = self.openai_client.responses.create(
            model=self.chat_model,
            instructions=system_instructions,
            input=user_input
        )
        
        # Extract token usage and cost
        usage = response.usage
        actual_cost = 0.0
        
        if usage:
            input_tokens = getattr(usage, 'input_tokens', 0)
            output_tokens = getattr(usage, 'output_tokens', 0)
            
            if DEBUG_MODE:
                print(f"[LLM Service] Tokens: {input_tokens} in, {output_tokens} out")
            
            actual_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M + \
                         (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
            
            self.usage_tracker.record_call(actual_cost)
        
        answer = response.output_text or "No answer generated"
        return answer, actual_cost
    
    # ==================== Stats & Cache Methods ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get API usage statistics"""
        usage_stats = self.usage_tracker.get_stats()
        cache_stats = self.response_cache.get_stats()
        
        return {
            "rate_limit": {
                "calls_last_minute": usage_stats['calls_last_minute'],
                "max_calls_per_minute": usage_stats['max_calls_per_minute']
            },
            "cost": {
                "daily_cost": usage_stats['daily_cost'],
                "max_daily_cost": usage_stats['max_daily_cost'],
                "reset_date": usage_stats['cost_reset_date']
            },
            "cache": {
                "cache_size": cache_stats['cache_size'],
                "ttl": cache_stats['ttl'],
                "enabled": cache_stats['enabled']
            }
        }
    
    def clear_cache(self):
        """Clear response cache"""
        self.response_cache.clear()
    
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
            if DEBUG_LLM:
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
        
        if DEBUG_LLM:
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
            if DEBUG_LLM:
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
    
    # ==================== Alert Summarization Methods ====================
    
    def summarize_alerts(self, combined_alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tóm tắt alerts từ ElastAlert2, Kibana Security và ML Predictions
        
        Args:
            combined_alert_data: Output từ ElasticsearchService.get_combined_alerts_for_daily_report()
        
        Returns:
            {
                "status": "success" | "error",
                "summary": "Tóm tắt bằng tiếng Việt...",
                "severity_level": "CRITICAL/HIGH/MEDIUM/LOW",
                "key_findings": [...],
                "recommended_actions": [...],
                "metadata": {...}
            }
        """
        # Load prompt configuration
        try:
            prompt_config = self._load_prompt_config("instructions/alert_summary.json")
        except FileNotFoundError as e:
            if DEBUG_LLM:
                print(f"[ERROR LLM] {str(e)}")
            return {
                "status": "error",
                "error": "Không tìm thấy file prompt config",
                "summary": "",
                "severity_level": "UNKNOWN"
            }
        
        # Extract data from combined_alert_data
        metadata = combined_alert_data.get('metadata', {})
        elastalert = combined_alert_data.get('elastalert', {})
        kibana = combined_alert_data.get('kibana_alerts', {})
        ml_predictions = combined_alert_data.get('ml_predictions', {})
        statistics = combined_alert_data.get('statistics', {})
        
        # Check if there are any alerts worth summarizing
        total_critical_alerts = metadata.get('total_alert_count', 0)
        ml_info_count = ml_predictions.get('by_severity', {}).get('INFO', {}).get('count', 0)
        
        if total_critical_alerts == 0:
            # No critical alerts - return a summary without LLM call
            summary_text = (
                f"**Tình hình bảo mật {metadata.get('time_range_hours', 24)}h qua: BÌNH THƯỜNG**\n\n"
                f"Không phát hiện cảnh báo nghiêm trọng nào:\n"
                f"- ElastAlert2 (Critical): 0\n"
                f"- Kibana Security Alerts: 0\n"
                f"- ML Classification EROR: 0\n"
                f"- ML Classification WARN: 0\n"
            )
            
            if ml_info_count > 0:
                summary_text += f"- ML Classification INFO (bình thường): {ml_info_count} logs\n"
            
            summary_text += "\n**Kết luận:** Hệ thống hoạt động ổn định, không cần hành động đặc biệt."
            
            return {
                "status": "success",
                "summary": summary_text,
                "severity_level": "LOW",
                "key_findings": ["Không có cảnh báo nghiêm trọng trong khoảng thời gian này"],
                "recommended_actions": ["Tiếp tục giám sát hệ thống theo lịch thường xuyên"],
                "metadata": {
                    "time_range_hours": metadata.get('time_range_hours', 24),
                    "total_alerts": 0,
                    "elastalert_count": 0,
                    "kibana_count": 0,
                    "ml_eror_count": 0,
                    "ml_warn_count": 0,
                    "ml_info_count": ml_info_count,
                    "generated_at": metadata.get('generated_at', ''),
                    "skipped_llm_call": True
                }
            }
        
        # Pre-compute compact stats (tối ưu token)
        compact_stats = self._prepare_alert_stats_for_llm(
            elastalert, kibana, ml_predictions, statistics, metadata
        )
        
        if DEBUG_LLM:
            print(f"[DEBUG LLM] Alert stats prepared: {len(json.dumps(compact_stats))} chars")
        
        # Build prompt
        settings = prompt_config.get('settings', {})
        max_tokens = settings.get('max_completion_tokens', 800)
        
        system_prompt = prompt_config.get('system_prompt', '')
        user_prompt_template = prompt_config.get('user_prompt_template', '')
        
        user_prompt = user_prompt_template.format(
            time_range=metadata.get('time_range_hours', 24),
            total_alerts=metadata.get('total_alert_count', 0),
            elastalert_count=metadata.get('elastalert_count', 0),
            kibana_count=metadata.get('kibana_alert_count', 0),
            ml_eror_count=metadata.get('ml_eror_count', 0),
            ml_warn_count=metadata.get('ml_warn_count', 0),
            elastalert_rules=compact_stats['elastalert_rules'],
            severity_distribution=compact_stats['severity_distribution'],
            ml_predictions_summary=compact_stats['ml_predictions_summary'],
            top_detection_rules=compact_stats['top_detection_rules'],
            top_attacked=compact_stats['top_attacked'],
            top_attackers=compact_stats['top_attackers'],
            event_distribution=compact_stats['event_distribution']
        )
        
        # Call OpenAI
        try:
            response = self.openai_client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=max_tokens
            )
            
            ai_text = response.choices[0].message.content or ""
            
            # Extract severity level from response
            severity_level = self._extract_severity_from_summary(ai_text)
            
            # Extract recommended actions
            actions = self._extract_recommendations(ai_text)
            
            # Calculate severity based on data if not found in response
            if severity_level == "UNKNOWN":
                severity_level = self._calculate_alert_severity(elastalert, kibana, ml_predictions)
            
            return {
                "status": "success",
                "summary": ai_text,
                "severity_level": severity_level,
                "key_findings": self._extract_key_findings_from_summary(ai_text),
                "recommended_actions": actions,
                "metadata": {
                    "time_range_hours": metadata.get('time_range_hours', 24),
                    "total_alerts": metadata.get('total_alert_count', 0),
                    "elastalert_count": metadata.get('elastalert_count', 0),
                    "kibana_count": metadata.get('kibana_alert_count', 0),
                    "ml_eror_count": metadata.get('ml_eror_count', 0),
                    "ml_warn_count": metadata.get('ml_warn_count', 0),
                    "generated_at": metadata.get('generated_at', '')
                }
            }
            
        except Exception as e:
            if DEBUG_LLM:
                print(f"[ERROR LLM] Alert summarization failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "summary": "",
                "severity_level": "UNKNOWN"
            }
    
    def _prepare_alert_stats_for_llm(
        self, 
        elastalert: Dict, 
        kibana: Dict,
        ml_predictions: Dict,
        statistics: Dict,
        metadata: Dict
    ) -> Dict[str, str]:
        """
        Chuẩn bị stats dạng compact text để giảm tokens
        
        Thay vì gửi raw JSON, convert thành bullet points ngắn gọn
        """
        # ElastAlert2 rules - chỉ top 5
        ea_rules = elastalert.get('summary', {}).get('count_by_rule', {})
        ea_rules_sorted = sorted(ea_rules.items(), key=lambda x: x[1], reverse=True)[:5]
        elastalert_rules = "\n".join([
            f"  - {rule}: {count} alerts" 
            for rule, count in ea_rules_sorted
        ]) if ea_rules_sorted else "  - Không có alert"
        
        # Kibana severity distribution
        severity_dist = kibana.get('total_by_severity', {})
        severity_distribution = ", ".join([
            f"{sev}: {count}" 
            for sev, count in severity_dist.items()
        ]) if severity_dist else "Không có data"
        
        # ML Predictions Summary
        ml_by_severity = ml_predictions.get('by_severity', {})
        ml_eror = ml_by_severity.get('EROR', {})
        ml_warn = ml_by_severity.get('WARNING', {})  # ES uses WARNING not WARN
        ml_info = ml_by_severity.get('INFO', {})
        
        ml_predictions_summary = (
            f"EROR (cần xử lý gấp): {ml_eror.get('count', 0)} logs (avg prob: {ml_eror.get('avg_probability', 0):.2f})\n"
            f"  WARNING (cần xem xét): {ml_warn.get('count', 0)} logs (avg prob: {ml_warn.get('avg_probability', 0):.2f})\n"
            f"  INFO (bình thường): {ml_info.get('count', 0)} logs"
        )
        
        # Add sample EROR logs if available (top 3)
        eror_samples = ml_eror.get('samples', [])[:3]
        if eror_samples:
            ml_predictions_summary += "\n  Top EROR logs:"
            for s in eror_samples:
                msg = s.get('message', '')[:100]
                prob = s.get('probability', 0)
                ml_predictions_summary += f"\n    - [{prob:.2f}] {msg}..."
        
        # Top detection rules - chỉ top 5
        top_rules = kibana.get('summary', {}).get('top_rules', [])[:5]
        top_detection_rules = "\n".join([
            f"  - {r['rule']}: {r['count']} hits"
            for r in top_rules
        ]) if top_rules else "  - Không có detection rules"
        
        # Top attacked/attacker IPs - chỉ top 5
        top_attacked_ips = statistics.get('top_attacked_ips', [])[:5]
        top_attacked = ", ".join([
            f"{ip['ip']} ({ip['hits']})"
            for ip in top_attacked_ips
        ]) if top_attacked_ips else "N/A"
        
        top_attacker_ips = statistics.get('top_attacker_ips', [])[:5]
        top_attackers = ", ".join([
            f"{ip['ip']} ({ip['hits']})"
            for ip in top_attacker_ips
        ]) if top_attacker_ips else "N/A"
        
        # Event distribution - chỉ top 5 categories
        event_dist = statistics.get('event_distribution', {})
        event_dist_sorted = sorted(event_dist.items(), key=lambda x: x[1], reverse=True)[:5]
        event_distribution = ", ".join([
            f"{cat}: {count}"
            for cat, count in event_dist_sorted
        ]) if event_dist_sorted else "N/A"
        
        return {
            "elastalert_rules": elastalert_rules,
            "severity_distribution": severity_distribution,
            "ml_predictions_summary": ml_predictions_summary,
            "top_detection_rules": top_detection_rules,
            "top_attacked": top_attacked,
            "top_attackers": top_attackers,
            "event_distribution": event_distribution
        }
    
    def _extract_severity_from_summary(self, ai_text: str) -> str:
        """Extract severity level từ AI response"""
        text_upper = ai_text.upper()
        
        # Tìm pattern "Mức độ nghiêm trọng: X" hoặc "Severity: X"
        if "CRITICAL" in text_upper:
            return "CRITICAL"
        elif "HIGH" in text_upper or "CAO" in text_upper:
            return "HIGH"
        elif "MEDIUM" in text_upper or "TRUNG BÌNH" in text_upper:
            return "MEDIUM"
        elif "LOW" in text_upper or "THẤP" in text_upper:
            return "LOW"
        
        return "UNKNOWN"
    
    def _extract_key_findings_from_summary(self, ai_text: str) -> list:
        """Extract key findings từ AI summary"""
        findings = []
        lines = ai_text.split('\n')
        
        in_findings_section = False
        for line in lines:
            line = line.strip()
            
            # Detect section headers
            if any(kw in line.lower() for kw in ['vấn đề', 'ưu tiên', 'finding', 'phát hiện']):
                in_findings_section = True
                continue
            
            if in_findings_section:
                if line.startswith(('-', '•', '*')) or (line and line[0].isdigit()):
                    finding = line.lstrip('-•*0123456789. ')
                    if len(finding) > 10:  # Skip too short lines
                        findings.append(finding)
                elif line == '' or any(kw in line.lower() for kw in ['đề xuất', 'action', 'hành động']):
                    in_findings_section = False
        
        return findings[:5]  # Top 5
    
    def _calculate_alert_severity(self, elastalert: Dict, kibana: Dict, ml_predictions: Optional[Dict] = None) -> str:
        """Calculate severity based on alert data including ML predictions"""
        ea_count = elastalert.get('total', 0)
        severity_dist = kibana.get('total_by_severity', {})
        
        critical_count = severity_dist.get('critical', 0)
        high_count = severity_dist.get('high', 0)
        
        # ML predictions - EROR is critical priority
        ml_eror_count = 0
        ml_warn_count = 0
        if ml_predictions:
            ml_by_severity = ml_predictions.get('by_severity', {})
            ml_eror_count = ml_by_severity.get('EROR', {}).get('count', 0)
            ml_warn_count = ml_by_severity.get('WARNING', {}).get('count', 0)  # ES uses WARNING
        
        # Logic: 
        # - Any critical alert or ML EROR > 5 = CRITICAL
        # - ElastAlert2 > 10 or High > 20 or ML EROR > 0 = HIGH
        # - ElastAlert2 > 0 or High > 5 or ML WARNING > 10 = MEDIUM
        # - Otherwise = LOW
        
        if critical_count > 0 or ml_eror_count > 5:
            return "CRITICAL"
        elif ea_count > 10 or high_count > 20 or ml_eror_count > 0:
            return "HIGH"
        elif ea_count > 0 or high_count > 5 or ml_warn_count > 10:
            return "MEDIUM"
        else:
            return "LOW"
