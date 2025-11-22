"""
RAG query processing with token usage tracking
Following OpenAI Python SDK best practices
"""
import os
import re
import hashlib
import time
import json
from typing import Optional, Dict, Any, List, cast
from datetime import datetime, timedelta
from openai import OpenAI, APIError, APIConnectionError, RateLimitError
from openai.types.chat import ChatCompletionMessageParam
from dotenv import load_dotenv
from config import (
    CHAT_MODEL, 
    DEFAULT_RESULTS, 
    INPUT_PRICE_PER_1M, 
    OUTPUT_PRICE_PER_1M,
    OPENAI_TIMEOUT,
    OPENAI_MAX_RETRIES,
    MAX_CALLS_PER_MINUTE,
    MAX_DAILY_COST,
    CACHE_ENABLED,
    CACHE_TTL
)
from anonymizer import DataAnonymizer

# Load environment variables
load_dotenv()

# Initialize OpenAI Client with proper configuration
# Following https://github.com/openai/openai-python best practices
client = OpenAI(
    # API key loaded from OPENAI_API_KEY environment variable (default behavior)
    api_key=os.environ.get("OPENAI_API_KEY"),
    timeout=OPENAI_TIMEOUT,
    max_retries=OPENAI_MAX_RETRIES,
)

# Initialize anonymizer for data protection
anonymizer = DataAnonymizer()

# Debug flag to show anonymization process
DEBUG_ANONYMIZATION = True  # Set to False to hide detailed logs

# API Safety tracking
class APIUsageTracker:
    """Track API usage for rate limiting and cost control"""
    def __init__(self):
        self.call_timestamps: List[float] = []
        self.daily_cost = 0.0
        self.cost_reset_date = datetime.now().date()
        self.cache: Dict[str, Dict[str, Any]] = {}
    
    def check_rate_limit(self) -> bool:
        """Check if we're within rate limit (calls per minute)"""
        now = time.time()
        # Remove timestamps older than 1 minute
        self.call_timestamps = [ts for ts in self.call_timestamps if now - ts < 60]
        
        if len(self.call_timestamps) >= MAX_CALLS_PER_MINUTE:
            wait_time = 60 - (now - self.call_timestamps[0])
            print(f"\n⚠️ Rate limit reached! Please wait {wait_time:.1f} seconds...")
            return False
        return True
    
    def check_daily_cost(self, estimated_cost: float) -> bool:
        """Check if adding this cost would exceed daily limit"""
        # Reset daily cost if it's a new day
        today = datetime.now().date()
        if today != self.cost_reset_date:
            self.daily_cost = 0.0
            self.cost_reset_date = today
        
        if self.daily_cost + estimated_cost > MAX_DAILY_COST:
            print(f"\n⚠️ Daily cost limit reached! (${self.daily_cost:.4f}/${MAX_DAILY_COST})")
            print(f"   This query would cost ~${estimated_cost:.4f}")
            print(f"   Limit will reset tomorrow.")
            return False
        return True
    
    def record_call(self, cost: float):
        """Record a successful API call"""
        self.call_timestamps.append(time.time())
        self.daily_cost += cost
    
    def get_cache_key(self, query: str, context_hash: str) -> str:
        """Generate cache key from query and context"""
        combined = f"{query}:{context_hash}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response if available and not expired"""
        if not CACHE_ENABLED:
            return None
        
        if cache_key in self.cache:
            cached_data = self.cache[cache_key]
            if time.time() - cached_data['timestamp'] < CACHE_TTL:
                print(f"\n💾 Cache hit! Using cached response (saved API call)")
                return cached_data['response']
            else:
                # Expired, remove from cache
                del self.cache[cache_key]
        return None
    
    def cache_response(self, cache_key: str, response: str):
        """Cache a response"""
        if CACHE_ENABLED:
            self.cache[cache_key] = {
                'response': response,
                'timestamp': time.time()
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current usage statistics"""
        return {
            'calls_last_minute': len(self.call_timestamps),
            'daily_cost': self.daily_cost,
            'cache_size': len(self.cache),
            'cost_reset_date': self.cost_reset_date.isoformat()
        }

# Global tracker instance
usage_tracker = APIUsageTracker()


def anonymize_text(text: str) -> str:
    """
    Anonymize sensitive information in text before sending to AI
    
    Args:
        text: Text containing potentially sensitive information
        
    Returns:
        Anonymized text with IP addresses and hostnames tokenized
    """
    # Anonymize IP addresses (matches IPv4 pattern)
    ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    text = re.sub(ip_pattern, lambda m: anonymizer.anonymize_ip(m.group(), method='token'), text)
    
    # Anonymize device IDs (pattern: xxx-01, xxx-xx-01)
    device_pattern = r'\b([a-z]+-(?:[a-z]+-)?\d+)\b'
    
    def anonymize_device(match):
        device_id = match.group(1)
        return anonymizer.anonymize_hostname(device_id, method='token')
    
    text = re.sub(device_pattern, anonymize_device, text)
    
    return text


def deanonymize_text(text: str) -> str:
    """
    De-anonymize text by replacing tokens with original values
    
    Args:
        text: Text containing anonymized tokens
        
    Returns:
        Text with original sensitive information restored
    """
    # Find all tokens (TKN-IP-xxx, HOST-xxx, etc.)
    token_pattern = r'(TKN-IP-[a-f0-9]+|HOST-[a-f0-9]+|USER-[a-f0-9]+|MAC-[a-f0-9]+)'
    
    def replace_token(match):
        token = match.group(1)
        original = anonymizer.deanonymize(token)
        return original if original else token  # Return token if no mapping found
    
    text = re.sub(token_pattern, replace_token, text)
    
    return text


def ask(collection, query: str, n_results: int = DEFAULT_RESULTS, filter_metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Search and answer questions with enhancements:
    - Increased results for more context
    - Metadata filtering support
    - Source citations
    - Token usage tracking
    - Rate limiting and cost control
    - Response caching
    
    Args:
        collection: ChromaDB collection instance
        query: User's question
        n_results: Number of documents to retrieve (default: 5, increased to 8 for better coverage)
        filter_metadata: Optional metadata filter
    
    Returns:
        Answer string with source citations
    """
    print(f"\n❓ Question: {query}")
    
    # === API SAFETY: Check rate limit ===
    if not usage_tracker.check_rate_limit():
        return "❌ Rate limit exceeded. Please wait a moment before trying again."
    
    # Increase n_results for comprehensive coverage (especially for SOC components questions)
    effective_n_results = max(n_results, 5)
    
    # Search with more results
    search_params = {
        "query_texts": [query],
        "n_results": effective_n_results
    }
    
    if filter_metadata:
        search_params["where"] = filter_metadata
    
    results = collection.query(**search_params)
    
    if not results["documents"] or not results["documents"][0]:
        return "Sorry, no relevant information found in the documentation."

    # Combine context with metadata
    context_list = results["documents"][0]
    metadatas_list = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []
    
    # Create context text with sources
    context_parts = []
    sources = set()
    
    for idx, (doc, meta, dist) in enumerate(zip(context_list, metadatas_list, distances)):
        context_parts.append(f"[Document {idx + 1}]\n{doc}")
        if meta and "source" in meta:
            sources.add(meta["source"])
    
    context_text = "\n\n---\n\n".join(context_parts)
    
    # Debug info
    print(f"\n📚 Found {len(context_list)} relevant documents")
    print(f"📄 Sources: {', '.join(sources)}")
    
    # === API SAFETY: Check cache ===
    context_hash = hashlib.md5(context_text.encode()).hexdigest()
    cache_key = usage_tracker.get_cache_key(query, context_hash)
    cached_response = usage_tracker.get_cached_response(cache_key)
    
    if cached_response:
        return cached_response
    
    # === DATA PROTECTION: Anonymize sensitive information ===
    # Before sending to AI, replace IPs and device IDs with tokens
    if DEBUG_ANONYMIZATION:
        print("\n" + "="*80)
        print("🔍 ANONYMIZATION DEBUG - CONTEXT BEFORE:")
        print("="*80)
        # Show first 500 chars of original context
        preview = context_text[:500] + "..." if len(context_text) > 500 else context_text
        print(preview)
        print("\n" + "="*80)
    
    context_text_anonymized = anonymize_text(context_text)
    
    ip_count = len(re.findall(r'TKN-IP-[a-f0-9]+', context_text_anonymized))
    host_count = len(re.findall(r'HOST-[a-f0-9]+', context_text_anonymized))
    print(f"🔒 Anonymization: {ip_count} IPs, {host_count} hostnames protected")
    
    if DEBUG_ANONYMIZATION:
        print("\n" + "="*80)
        print("🔒 ANONYMIZATION DEBUG - CONTEXT AFTER (sent to OpenAI):")
        print("="*80)
        # Show first 500 chars of anonymized context
        preview = context_text_anonymized[:500] + "..." if len(context_text_anonymized) > 500 else context_text_anonymized
        print(preview)
        print("\n" + "="*80)
        print("\n⚠️  NO REAL IPs OR DEVICE NAMES IN ABOVE TEXT - All replaced with tokens!")
        print("="*80)

    # Build messages following OpenAI's recommended structure
    # Using 'system' role for instructions and 'user' role for the query
    messages: List[ChatCompletionMessageParam] = [
        {
            "role": "system", 
            "content": """You are a SOC (Security Operations Center) expert with deep knowledge of Cyberfortress Ecosystem and cybersecurity in general.

Key capabilities:
- Answer questions about the Cyberfortress infrastructure based on provided context
- Provide general cybersecurity knowledge when asked about concepts, tools, or best practices
- Support both English and Vietnamese languages - detect user's language and respond in the same language
- Be helpful and educational while being technically accurate

IMPORTANT: The context contains anonymized tokens (TKN-IP-xxx, HOST-xxx) for security. Treat them as actual IP addresses and device names in your response."""
        },
        {
            "role": "user", 
            "content": f"""Please answer the following question. Use the CONTEXT below if it's relevant to the question.

IMPORTANT GUIDELINES:
1. **Language**: Detect the question language and respond in the SAME language (English or Vietnamese)
2. **Context-based questions**: If the question is about Cyberfortress infrastructure, use the CONTEXT below
3. **General questions**: If asking about general cybersecurity concepts, tools, or best practices (not in context), answer using your general knowledge
4. **Mixed approach**: Combine context information with general knowledge when appropriate
5. **Accuracy**: Always be technically accurate. If unsure about Cyberfortress-specific details not in context, say "Not mentioned in the documentation"
6. **Citations**: When using context, cite the anonymized tokens (e.g., TKN-IP-xxx, HOST-xxx) as if they were real values
7. **Anonymized data**: Treat TKN-IP-xxx as IP addresses and HOST-xxx as device names in your response

CONTEXT (Cyberfortress Infrastructure - Anonymized for Security):
{context_text_anonymized}

QUESTION:
{query}

Please provide a clear, detailed answer in the same language as the question."""
        }
    ]
    
    # Make API call with error handling
    # Following https://platform.openai.com/docs/guides/error-codes
    try:
        # === API SAFETY: Estimate cost before calling ===
        # Rough estimate: ~1 token per 4 characters for English, ~1 per 2 for Vietnamese
        estimated_prompt_tokens = len(context_text_anonymized) // 3 + len(query) // 3
        estimated_completion_tokens = 500  # Conservative estimate
        estimated_cost = (estimated_prompt_tokens / 1_000_000) * INPUT_PRICE_PER_1M + \
                        (estimated_completion_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
        
        if not usage_tracker.check_daily_cost(estimated_cost):
            return "❌ Daily cost limit reached. Please try again tomorrow."
        
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages
            # Note: gpt-5-mini only supports default temperature=1, custom values cause 400 error
        )
        
        # Extract token usage
        usage = response.usage
        actual_cost = 0.0
        if usage:
            print(f"\n💰 Token Usage:")
            print(f"   - Prompt tokens: {usage.prompt_tokens}")
            print(f"   - Completion tokens: {usage.completion_tokens}")
            print(f"   - Total tokens: {usage.total_tokens}")
            
            # Calculate actual cost
            input_cost = (usage.prompt_tokens / 1_000_000) * INPUT_PRICE_PER_1M
            output_cost = (usage.completion_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
            actual_cost = input_cost + output_cost
            print(f"   - Estimated cost: ${actual_cost:.6f}")
            
            # Record the call
            usage_tracker.record_call(actual_cost)
            
            # Show daily usage stats
            stats = usage_tracker.get_stats()
            print(f"\n📊 Today's Usage:")
            print(f"   - Total cost: ${stats['daily_cost']:.4f} / ${MAX_DAILY_COST}")
            print(f"   - Calls in last minute: {stats['calls_last_minute']} / {MAX_CALLS_PER_MINUTE}")
            print(f"   - Cache entries: {stats['cache_size']}")
        
        answer_with_tokens = response.choices[0].message.content or "No answer generated"
        
        if DEBUG_ANONYMIZATION:
            print("\n" + "="*80)
            print("🤖 AI RESPONSE (with anonymized tokens):")
            print("="*80)
            print(answer_with_tokens)
            print("\n" + "="*80)
        
        # === DATA PROTECTION: De-anonymize response ===
        # Replace tokens with original values before showing to user
        answer = deanonymize_text(answer_with_tokens)
        
        if DEBUG_ANONYMIZATION:
            print("\n" + "="*80)
            print("✅ FINAL ANSWER (de-anonymized for user):")
            print("="*80)
            print(answer)
            print("\n" + "="*80)
        
        # Add source citations
        if sources:
            answer += f"\n\n📚 Sources: {', '.join(sorted(sources))}"
        
        # === API SAFETY: Cache the response ===
        usage_tracker.cache_response(cache_key, answer)
        
        return answer
        
    except RateLimitError as e:
        error_msg = f"Rate limit exceeded. Please try again later. (Request ID: {getattr(e, 'request_id', 'N/A')})"
        print(f"\n❌ {error_msg}")
        return error_msg
        
    except APIConnectionError as e:
        error_msg = f"Connection error: {str(e)}. Please check your internet connection."
        print(f"\n❌ {error_msg}")
        return error_msg
        
    except APIError as e:
        error_msg = f"OpenAI API error: {str(e)} (Request ID: {getattr(e, 'request_id', 'N/A')})"
        print(f"\n❌ {error_msg}")
        return error_msg
