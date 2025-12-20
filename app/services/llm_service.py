"""
LLM Service - AI Analysis for RAG queries and IntelOwl results
"""
import os
import re
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from openai import APIError, APIConnectionError, RateLimitError
from dotenv import load_dotenv
from app.config import *
from app.core.openai_client import get_openai_client

# Import analyzer registry
from app.services.analyzers import get_handler, get_all_handlers, get_registered_analyzer_names

# Setup module-level logger
logger = logging.getLogger('smartxdr.llm')

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
        
        import logging
        logger = logging.getLogger('smartxdr.llm')
        
        try:
            # Use shared OpenAI client
            self.openai_client = get_openai_client()
            self.chat_model = CHAT_MODEL
            self.prompts_dir = PROJECT_ROOT / "prompts"
            
            # Initialize utilities
            from app.utils.rate_limit import APIUsageTracker
            from app.utils.cache import ResponseCache
            from app.services.prompt_builder_service import PromptBuilder
            
            logger.info("Initializing LLM Service components...")
            
            self.usage_tracker = APIUsageTracker(
                max_calls_per_minute=MAX_CALLS_PER_MINUTE,
                max_daily_cost=MAX_DAILY_COST
            )
            logger.info("APIUsageTracker initialized")
            
            # Enable semantic cache for better hit rate on similar questions
            from app.config import SEMANTIC_CACHE_ENABLED
            self.response_cache = ResponseCache(
                ttl=CACHE_TTL, 
                enabled=CACHE_ENABLED,
                use_semantic_cache=SEMANTIC_CACHE_ENABLED
            )
            logger.info(f"ResponseCache initialized (semantic_cache={SEMANTIC_CACHE_ENABLED})")
            
            self.prompt_builder = PromptBuilder(prompt_file='rag_system.json')
            logger.info("PromptBuilder initialized")
            
            self._initialized = True
            logger.info("LLMService fully initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize LLMService: {e}", exc_info=True)
            self._initialized = False
            raise
    
    # ==================== IOC Enrichment Methods ====================
    
    def summarize_for_ioc_description(self, comment_text: str, max_length: int = 200) -> str:
        """
        Tóm tắt SmartXDR comment thành description ngắn gọn cho IOC
        
        Uses:
        - prompts/instructions/ioc_description_summary.json for prompt
        - SUMMARY_MODEL for faster/cheaper summarization
        
        Args:
            comment_text: Full comment text từ SmartXDR AI Analysis
            max_length: Maximum length của summary (default: 200 chars)
        
        Returns:
            Concise summary string for IOC description
        """
        if not comment_text:
            return ""
        
        # Remove the [SmartXDR AI Analysis] header if present
        clean_text = comment_text.replace("[SmartXDR AI Analysis]", "").strip()
        
        # If already short enough, just clean it
        if len(clean_text) <= max_length:
            return clean_text
        
        # Load prompt from file
        system_prompt, user_template = self._load_ioc_summary_prompt()
        user_prompt = user_template.format(content=clean_text[:2000])
        
        # Use LLM to summarize with SUMMARY_MODEL
        try:
            from app.config import SUMMARY_MODEL
            
            response = self.openai_client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=500  # Allow longer summaries
            )
            
            summary = response.choices[0].message.content.strip()
            
            # Ensure max length
            if len(summary) > max_length:
                summary = summary[:max_length-3] + "..."
            
            return summary
            
        except Exception as e:
            logger.warning(f"Failed to summarize comment: {e}")
            # Fallback: truncate the original text
            return clean_text[:max_length-3] + "..." if len(clean_text) > max_length else clean_text
    
    def _load_ioc_summary_prompt(self) -> tuple:
        """
        Load IOC summary prompt from JSON file
        
        Returns:
            Tuple of (system_prompt, user_prompt_template)
        """
        import json
        
        prompt_file = self.prompts_dir / "instructions" / "ioc_description_summary.json"
        
        # Fallback prompts if file not found
        fallback_system = """Bạn là AI assistant chuyên tóm tắt báo cáo phân tích IOC.
Nhiệm vụ: Tóm tắt nội dung phân tích thành 1-2 câu ngắn gọn (tối đa 200 ký tự).
Tập trung vào: mức độ nguy hiểm, loại threat, và recommendation chính.
Chỉ trả về text summary, không thêm prefix hay formatting."""
        fallback_user = "Tóm tắt phân tích IOC sau:\n\n{content}"
        
        try:
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return (
                    data.get('system_prompt', fallback_system),
                    data.get('user_prompt_template', fallback_user)
                )
        except Exception as e:
            logger.warning(f"Failed to load IOC summary prompt: {e}")
        
        return (fallback_system, fallback_user)
    
    # ==================== RAG Query Methods ====================
    
    def ask_rag(
        self,
        query: str,
        top_k: int = DEFAULT_RESULTS,
        filters: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        RAG Query - Search and answer questions using RAGService
        
        Args:
            query: User's question
            top_k: Number of documents to retrieve
            filters: Optional metadata filters (e.g., {"is_active": True, "tags": "security"})
            use_cache: Whether to use cache (default: True). Set False for queries with dynamic context.
            session_id: Optional session ID for conversation memory. If provided, enables:
                - Including recent conversation history in context
                - Storing messages for future reference
                - Semantic search for relevant past conversations
        
        Returns:
            {
                "status": "success" | "error",
                "answer": "...",
                "cached": bool,
                "sources": [...],
                "session_id": "..." (if session was used),
                "error": "..." (if error)
            }
        """
        if DEBUG_MODE:
            logger.debug(f"Question: {query}")
            if session_id:
                print(f"[LLM Service] Session: {session_id[:8]}...")
        
        # Check rate limit
        if not self.usage_tracker.check_rate_limit():
            return {
                "status": "error",
                "error": "Rate limit exceeded. Please wait a moment before trying again.",
                "error_type": "rate_limit"
            }
        
        # Import RAGService
        from app.rag.service import RAGService
        rag_service = RAGService()
        
        # Initialize conversation memory if session_id provided
        conversation_memory = None
        conversation_history_text = ""
        
        if session_id:
            try:
                from app.services.conversation_memory import get_conversation_memory
                conversation_memory = get_conversation_memory()
                
                # Use LangChain-formatted history for better context (token-aware windowing)
                # Falls back to summarized history if LangChain not available
                conversation_history_text = conversation_memory.format_langchain_history(session_id)
                
                # If LangChain format returns empty, try summarized history
                if not conversation_history_text:
                    conversation_history_text = conversation_memory.get_summarized_history(session_id)
                
                if conversation_history_text and DEBUG_MODE:
                    is_summary = "Previous conversation summary:" in conversation_history_text
                    is_langchain = "Previous conversation:" in conversation_history_text
                    format_type = "LANGCHAIN" if is_langchain else ("SUMMARY" if is_summary else "RAW")
                    print(f"[LLM Service] History: {format_type} ({len(conversation_history_text)} chars)")
                    print(f"[LLM Service] Content preview: {conversation_history_text[:150]}...")
                    
            except Exception as e:
                if DEBUG_MODE:
                    print(f"[LLM Service] Conversation memory error: {e}")
                # Continue without conversation memory
        
        # Check cache (semantic + exact match)
        # Cache works even with session_id - helps with repeated questions
        if use_cache:
            cache_key = self.response_cache.get_cache_key(query, "")
            cached_response = self.response_cache.get(cache_key, query)
            
            if cached_response:
                if DEBUG_MODE:
                    print(f"[LLM Service] CACHE HIT for: {query[:50]}...")
                # Get sources from RAG for cached response
                query_result = rag_service.query(query, top_k, filters)
                
                # Still store in conversation memory for context continuity
                if session_id and conversation_memory:
                    try:
                        conversation_memory.add_message(session_id, "user", query)
                        conversation_memory.add_message(session_id, "assistant", cached_response, {"cached": True})
                    except:
                        pass
                
                result = {
                    "status": "success",
                    "answer": cached_response,
                    "cached": True,
                    "sources": query_result.get("sources", [])
                }
                if session_id:
                    result["session_id"] = session_id
                return result
        
        # Build context using RAGService
        # Enhance query with conversation context for better RAG search
        rag_query = query
        if conversation_history_text:
            # Extract key entities from history to enhance RAG query
            context_entities = self._extract_context_entities(conversation_history_text)
            if context_entities:
                rag_query = f"{query} (context: {context_entities})"
                if DEBUG_MODE:
                    print(f"[LLM Service] Enhanced RAG query: {rag_query[:100]}...")
        
        context_text, sources = rag_service.build_context_from_query(
            query_text=rag_query,
            top_k=top_k,
            filters=filters
        )
        
        # Combine RAG context with conversation history
        if conversation_history_text:
            enhanced_context = f"{conversation_history_text}\n\n---\n\n{context_text}"
        else:
            enhanced_context = context_text
        
        # Build API request
        system_instructions = self.prompt_builder.build_rag_prompt()
        user_input = self._build_rag_user_input(enhanced_context, query)
        
        # Call API
        try:
            answer_with_tokens, actual_cost = self._call_responses_api(
                system_instructions,
                user_input
            )
            
            answer = answer_with_tokens
            
            # Add source citations
            # if sources:
            #     answer += f"\n\nSources: {', '.join(sorted(sources))}"
            
            # Cache the response (only if use_cache=True and no session)
            if use_cache and not session_id:
                cache_key = self.response_cache.get_cache_key(query, "")
                self.response_cache.set(cache_key, answer, query)
            
            # Store in conversation memory if session_id provided
            if session_id and conversation_memory:
                try:
                    # Store user message
                    conversation_memory.add_message(
                        session_id=session_id,
                        role="user",
                        content=query,
                        metadata={"sources_count": len(sources) if sources else 0}
                    )
                    
                    # Store assistant response
                    conversation_memory.add_message(
                        session_id=session_id,
                        role="assistant",
                        content=answer,
                        metadata={"sources": list(sources) if sources else [], "cost": actual_cost}
                    )
                except Exception as e:
                    if DEBUG_MODE:
                        print(f"[LLM Service] Failed to store in conversation memory: {e}")
            
            result = {
                "status": "success",
                "answer": answer,
                "cached": False,
                "sources": list(sources),
                "cost": actual_cost
            }
            
            # Include session_id in response if used
            if session_id:
                result["session_id"] = session_id
            
            return result
            
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
    
    def _build_rag_user_input(self, context: str, query: str) -> str:
        """Build user input for RAG query"""
        user_prompt_template = self.prompt_builder.build_user_input_prompt()
        return user_prompt_template.format(context=context, query=query)
    
    def _generate_answer_from_context(
        self, 
        query: str, 
        context: str, 
        sources: list = None,
        use_cache: bool = True
    ) -> dict:
        """
        Generate LLM answer using pre-fetched context.
        
        This avoids duplicate RAG queries when context is already available.
        Used by /api/rag/query endpoint.
        
        Args:
            query: User's question
            context: Pre-built context from RAG query
            sources: List of source documents
            use_cache: Whether to use response cache
            
        Returns:
            Dict with answer, cached status, etc.
        """
        sources = sources or []
        
        # Check cache first
        if use_cache:
            cache_key = self.response_cache.get_cache_key(query, "")
            cached_response = self.response_cache.get(cache_key, query)
            if cached_response:
                return {
                    "status": "success",
                    "answer": cached_response,
                    "cached": True,
                    "sources": sources
                }
        
        # Build API request
        system_instructions = self.prompt_builder.build_rag_prompt()
        user_input = self._build_rag_user_input(context, query)
        
        try:
            # Call API
            answer, actual_cost = self._call_responses_api(
                system_instructions,
                user_input
            )
            
            # Cache the response
            if use_cache:
                cache_key = self.response_cache.get_cache_key(query, "")
                self.response_cache.set(cache_key, answer, query)
            
            return {
                "status": "success",
                "answer": answer,
                "cached": False,
                "sources": sources,
                "cost": actual_cost
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "answer": f"Error generating answer: {str(e)}"
            }
    
    def _extract_context_entities(self, history_text: str) -> str:
        """
        Extract key entities from conversation history using LLM for query enhancement.
        
        Uses prompts/instructions/context_extraction.json for scalable entity extraction.
        Falls back to simple keyword matching if LLM unavailable.
        """
        # Try LLM-based extraction first
        try:
            entities = self._llm_extract_entities(history_text)
            if entities:
                return entities
        except Exception as e:
            if DEBUG_MODE:
                print(f"[LLM Service] LLM entity extraction failed: {e}, using fallback")
        
        # Fallback: simple keyword matching
        return self._simple_entity_extraction(history_text)
    
    def _llm_extract_entities(self, history_text: str) -> str:
        """Use LLM to extract context entities from conversation history."""
        import json
        
        try:
            from app.services.prompt_builder_service import PromptBuilder
            
            # Load prompt from JSON
            builder = PromptBuilder()
            prompt_json = builder.build_task_prompt("context_extraction")
            prompt_data = json.loads(prompt_json)
            
            system_prompt = prompt_data.get("system_prompt", "Extract key entities from this conversation.")
            settings = prompt_data.get("settings", {})
            max_tokens = settings.get("max_completion_tokens", 30)
            
            # Call LLM
            response = self.openai_client.chat.completions.create(
                model=SUMMARY_MODEL,  # Use cheap model
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": history_text[:500]}  # Limit input
                ],
                max_completion_tokens=max_tokens
            )
            
            entities = response.choices[0].message.content.strip()
            
            # Clean up - remove punctuation and limit length
            entities = ' '.join(entities.split()[:5])
            
            if DEBUG_MODE and entities:
                print(f"[LLM Service] Extracted entities: {entities}")
            
            return entities
            
        except FileNotFoundError:
            return ""
        except Exception as e:
            raise e
    
    def _simple_entity_extraction(self, history_text: str) -> str:
        """
        Fallback: Simple keyword extraction without LLM.
        Extracts system names, IPs, and device IDs from conversation history.
        """
        import re
        
        entities = []
        
        # 1. Known system/device names (expanded list)
        systems = [
            'SIEM', 'Wazuh', 'pfSense', 'Zeek', 'IRIS', 'Elastic', 'Elasticsearch', 'Kibana',
            'Router', 'Firewall', 'Server', 'Linux', 'Windows', 'n8n', 'MISP', 'SOAR',
            'Suricata', 'NAT', 'Gateway', 'Switch', 'IDPS', 'IDS', 'IPS', 'Elastalert',
            'WAF', 'DVWA', 'Attacker', 'Victim', 'Windows Server'
        ]
        
        for system in systems:
            if re.search(rf'\b{system}\b', history_text, re.IGNORECASE):
                entities.append(system)
                if len(entities) >= 3:  # Max 3 system names
                    break
        
        # 2. Extract IP addresses
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ips = re.findall(ip_pattern, history_text)
        if ips:
            unique_ips = list(dict.fromkeys(ips))[:2]  # Max 2 IPs
            entities.extend([f"IP {ip}" for ip in unique_ips])
        
        # 3. Extract device IDs (e.g., suricata-01, pfsense-01)
        device_id_pattern = r'\b([a-z]+-\d{2})\b'
        device_ids = re.findall(device_id_pattern, history_text, re.IGNORECASE)
        if device_ids:
            unique_ids = list(dict.fromkeys(device_ids))[:2]
            entities.extend(unique_ids)
        
        return ' '.join(entities[:5])  # Max 5 entities total
    
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
        Tích hợp RAG để đưa ra gợi ý phù hợp với ngữ cảnh hệ thống.
        
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
        
        # **RAG ENHANCEMENT: Lấy context từ knowledge base để đưa ra gợi ý phù hợp với hệ thống**
        rag_context = self._get_rag_context_for_ioc(ioc_value, stats, critical_findings)
        
        # Build prompt from template
        user_prompt_template = prompt_config.get('user_prompt_template', '')
        system_prompt = prompt_config.get('system_prompt', 'You are a cybersecurity expert.')
        
        # Enhance system prompt with RAG context if available
        if rag_context:
            system_prompt += f"\n\n**SYSTEM CONTEXT (từ knowledge base của tổ chức):**\n{rag_context}\n\nHãy sử dụng thông tin này để đưa ra gợi ý phù hợp với hệ thống cụ thể của tổ chức."
        
        prompt = user_prompt_template.format(
            ioc_value=ioc_value,
            total_analyzers=total_analyzers,
            successful_count=successful_count,
            connector_count=len(connector_reports),
            analyzer_findings=json.dumps(critical_findings, indent=2, ensure_ascii=False),
            threat_stats=json.dumps(stats, indent=2, ensure_ascii=False)
        )
        
        if DEBUG_LLM:
            print(f"[DEBUG LLM] IOC Enrichment prompt length: {len(prompt)}")
            print(f"[DEBUG LLM] System prompt: {system_prompt[:100]}...")
            print(f"[DEBUG LLM] User prompt preview: {prompt[:500]}...")
            if rag_context:
                print(f"[DEBUG LLM] RAG context length: {len(rag_context)} chars")
        
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
            
            if DEBUG_LLM:
                print(f"[DEBUG LLM] IOC Response length: {len(ai_text)}")
                print(f"[DEBUG LLM] IOC Response preview: {ai_text[:200]}...")
                print(f"[DEBUG LLM] Finish reason: {response.choices[0].finish_reason}")
            
            # Check for empty response
            if not ai_text:
                print(f"[WARNING LLM] Empty response for IOC {ioc_value}")
                print(f"[WARNING LLM] Full response object: {response}")
                ai_text = f"Không thể phân tích IOC {ioc_value} - API trả về rỗng"
            
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
    
    def _get_rag_context_for_ioc(self, ioc_value: str, stats: dict, findings: list) -> str:
        """
        Lấy context từ RAG để đưa ra gợi ý phù hợp với ngữ cảnh hệ thống.
        
        Args:
            ioc_value: Giá trị IOC (IP/domain/hash/url)
            stats: Threat statistics đã tính
            findings: Critical findings từ analyzers
        
        Returns:
            Context text từ RAG hoặc empty string nếu không có
        """
        try:
            from app.rag.service import RAGService
            rag_service = RAGService()
            
            # Xây dựng query dựa trên IOC và threat info
            # Tập trung vào các khía cạnh liên quan đến cấu hình hệ thống và response procedures
            query_parts = []
            
            # Determine IOC type and add relevant context
            if self._is_ip_address(ioc_value):
                query_parts.append("IP address threat response firewall rules network policy")
            elif self._is_domain(ioc_value):
                query_parts.append("domain DNS blocking threat intelligence MISP")
            elif self._is_hash(ioc_value):
                query_parts.append("malware hash file detection endpoint security Wazuh")
            else:
                query_parts.append("threat detection security response")
            
            # Add risk level context
            max_risk = stats.get('max_risk_score', 0)
            if max_risk >= 80:
                query_parts.append("critical incident response isolation containment")
            elif max_risk >= 60:
                query_parts.append("high risk alert investigation")
            elif max_risk >= 30:
                query_parts.append("medium risk monitoring")
            
            # Add analyzer-specific context
            analyzer_stats = stats.get('analyzer_stats', {})
            if 'VirusTotal' in str(analyzer_stats):
                query_parts.append("antivirus detection malware signature")
            if 'AbuseIPDB' in str(analyzer_stats):
                query_parts.append("IP reputation abuse reports")
            
            # Build query
            rag_query = " ".join(query_parts)
            
            if DEBUG_LLM:
                print(f"[DEBUG LLM] RAG query for IOC context: {rag_query[:100]}...")
            
            # Query RAG với top_k nhỏ để tập trung vào context quan trọng nhất
            context_text, sources = rag_service.build_context_from_query(
                query_text=rag_query,
                top_k=5,  # Lấy 5 documents liên quan nhất
                filters={"is_active": True}
            )
            
            # Nếu không tìm thấy context phù hợp
            if context_text == "No relevant context found." or not context_text.strip():
                if DEBUG_LLM:
                    print(f"[DEBUG LLM] No RAG context found for IOC")
                return ""
            
            if DEBUG_LLM:
                print(f"[DEBUG LLM] RAG context sources: {sources}")
            
            # Truncate context nếu quá dài (giữ token usage hợp lý)
            max_context_chars = 1500
            if len(context_text) > max_context_chars:
                context_text = context_text[:max_context_chars] + "..."
            
            return context_text
            
        except Exception as e:
            if DEBUG_LLM:
                print(f"[DEBUG LLM] RAG context error: {e}")
            return ""
    
    def _is_ip_address(self, value: str) -> bool:
        """Check if value is an IP address using ipaddress module (built-in)"""
        import ipaddress
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False
    
    def _is_domain(self, value: str) -> bool:
        """Check if value is a domain using urllib.parse (built-in)"""
        from urllib.parse import urlparse
        
        # Skip if it's an IP address
        if self._is_ip_address(value):
            return False
        
        # Check basic domain structure
        if '.' not in value:
            return False
        
        # Try to parse as URL (add scheme if missing)
        try:
            test_url = f"http://{value}" if not value.startswith(('http://', 'https://')) else value
            parsed = urlparse(test_url)
            hostname = parsed.hostname or value
            
            # Domain validation: must have valid characters and TLD
            parts = hostname.split('.')
            if len(parts) < 2:
                return False
            
            # Each part must be alphanumeric with hyphens (not at start/end)
            for part in parts:
                if not part or part.startswith('-') or part.endswith('-'):
                    return False
                if not all(c.isalnum() or c == '-' for c in part):
                    return False
            
            # TLD should be at least 2 chars and alphabetic
            tld = parts[-1]
            if len(tld) < 2 or not tld.isalpha():
                return False
            
            return True
        except Exception:
            return False
    
    def _is_hash(self, value: str) -> bool:
        """Check if value is a hash (MD5, SHA1, SHA256) using hashlib for reference"""
        import hashlib
        
        # Hash lengths: MD5=32, SHA1=40, SHA256=64
        valid_lengths = {32, 40, 64}  # hashlib.md5().hexdigest() length, etc.
        
        if len(value) not in valid_lengths:
            return False
        
        # Must be valid hexadecimal
        try:
            int(value, 16)
            return True
        except ValueError:
            return False
    
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
                try:
                    # Extract stats using handler
                    analyzer_stats = handler.extract_stats(report)
                    stats["analyzer_stats"][handler.display_name] = analyzer_stats
                    
                    # Update risk score
                    risk_score = handler.get_risk_score(report)
                    stats["max_risk_score"] = max(stats["max_risk_score"], risk_score)
                    
                    # Count malicious
                    if handler.is_malicious(report):
                        stats["malicious_count"] += 1
                except Exception as e:
                    # Log error but continue processing other analyzers
                    stats["analyzer_stats"][handler.display_name] = {"error": str(e)}
        
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
                try:
                    summary = handler.summarize(analyzer)
                    if summary:
                        findings_with_priority.append({
                            "priority": handler.priority,
                            "finding": summary
                        })
                except Exception as e:
                    # Log error but continue processing
                    pass
        
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
            if line.startswith('-') or line.startswith('') or (line and line[0].isdigit() and '.' in line):
                recommendations.append(line.lstrip('-0123456789. '))
        
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
            if DEBUG_LLM:
                print(f"[DEBUG LLM] Calling OpenAI for alert summary...")
                print(f"[DEBUG LLM] System prompt length: {len(system_prompt)}")
                print(f"[DEBUG LLM] User prompt length: {len(user_prompt)}")
            
            response = self.openai_client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_completion_tokens=max_tokens
            )
            
            ai_text = response.choices[0].message.content or ""
            
            if DEBUG_LLM:
                print(f"[DEBUG LLM] Response received, length: {len(ai_text)}")
                print(f"[DEBUG LLM] Finish reason: {response.choices[0].finish_reason}")
                if not ai_text:
                    print(f"[DEBUG LLM] WARNING: Empty response from OpenAI!")
                    print(f"[DEBUG LLM] Full response: {response}")
            
            # Check for empty response
            if not ai_text:
                # Log the issue and return calculated severity
                print(f"[WARNING] OpenAI returned empty content. Finish reason: {response.choices[0].finish_reason}")
                severity_level = self._calculate_alert_severity(elastalert, kibana, ml_predictions)
                return {
                    "status": "success",
                    "summary": f"[Không thể tạo tóm tắt - API response trống]\n\nDữ liệu thống kê:\n- ElastAlert2: {metadata.get('elastalert_count', 0)} alerts\n- Kibana Security: {metadata.get('kibana_alert_count', 0)} alerts\n- ML ERROR: {metadata.get('ml_eror_count', 0)}\n- ML WARNING: {metadata.get('ml_warn_count', 0)}",
                    "severity_level": severity_level,
                    "key_findings": [],
                    "recommended_actions": [],
                    "metadata": {
                        "time_range_hours": metadata.get('time_range_hours', 24),
                        "total_alerts": metadata.get('total_alert_count', 0),
                        "elastalert_count": metadata.get('elastalert_count', 0),
                        "kibana_count": metadata.get('kibana_alert_count', 0),
                        "ml_eror_count": metadata.get('ml_eror_count', 0),
                        "ml_warn_count": metadata.get('ml_warn_count', 0),
                        "generated_at": metadata.get('generated_at', ''),
                        "api_issue": "empty_response"
                    }
                }
            
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
        ml_error = ml_by_severity.get('ERROR', {})  # ES uses ERROR not EROR
        ml_warn = ml_by_severity.get('WARNING', {})  # ES uses WARNING not WARN
        ml_info = ml_by_severity.get('INFO', {})
        
        ml_predictions_summary = (
            f"ERROR (cần xử lý gấp): {ml_error.get('count', 0)} logs (avg prob: {ml_error.get('avg_probability', 0):.2f})\n"
            f"  WARNING (cần xem xét): {ml_warn.get('count', 0)} logs (avg prob: {ml_warn.get('avg_probability', 0):.2f})\n"
            f"  INFO (bình thường): {ml_info.get('count', 0)} logs"
        )
        
        # Add sample ERROR logs if available (top 3)
        error_samples = ml_error.get('samples', [])[:3]
        if error_samples:
            ml_predictions_summary += "\n  Top ERROR logs:"
            for s in error_samples:
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
                if line.startswith(('-', '', '*')) or (line and line[0].isdigit()):
                    finding = line.lstrip('-*0123456789. ')
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
        
        # ML predictions - ERROR is critical priority
        ml_error_count = 0
        ml_warn_count = 0
        if ml_predictions:
            ml_by_severity = ml_predictions.get('by_severity', {})
            ml_error_count = ml_by_severity.get('ERROR', {}).get('count', 0)  # ES uses ERROR
            ml_warn_count = ml_by_severity.get('WARNING', {}).get('count', 0)  # ES uses WARNING
        
        # Logic: 
        # - Any critical alert or ML ERROR > 5 = CRITICAL
        # - ElastAlert2 > 10 or High > 20 or ML ERROR > 0 = HIGH
        # - ElastAlert2 > 0 or High > 5 or ML WARNING > 10 = MEDIUM
        # - Otherwise = LOW
        
        if critical_count > 0 or ml_error_count > 5:
            return "CRITICAL"
        elif ea_count > 10 or high_count > 20 or ml_error_count > 0:
            return "HIGH"
        elif ea_count > 0 or high_count > 5 or ml_warn_count > 10:
            return "MEDIUM"
        else:
            return "LOW"
