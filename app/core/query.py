"""
RAG query processing with token usage tracking
Following OpenAI Python SDK best practices - using Responses API
"""
import os
import re
import hashlib
import time
import json
from typing import Optional, Dict, Any, List, cast
from datetime import datetime, timedelta
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
    DEBUG_MODE
)
from app.core.anonymizer import DataAnonymizer
from app.services.prompt_builder_service import PromptBuilder
from app.utils.rate_limit import APIUsageTracker
from app.utils.cache import ResponseCache

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

# Initialize PromptBuilder for system prompts (using RAG-optimized prompt)
prompt_builder = PromptBuilder(prompt_file='rag_system.json')

# Initialize API usage tracker and cache
usage_tracker = APIUsageTracker(
    max_calls_per_minute=MAX_CALLS_PER_MINUTE,
    max_daily_cost=MAX_DAILY_COST
)
response_cache = ResponseCache(ttl=CACHE_TTL, enabled=CACHE_ENABLED)

# Debug flag to show anonymization process
DEBUG_ANONYMIZATION = False  # Set to True to see detailed logs


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


def _search_and_build_context(collection, query: str, n_results: int, filter_metadata: Optional[Dict[str, Any]] = None) -> tuple[str, set[str], list[str]]:
    """
    Search collection and build context from results
    
    Returns:
        Tuple of (context_text, sources, context_list)
    """
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
    min_distance = "N/A"
    
    if results["documents"] and results["documents"][0]:
        num_found = len(results["documents"][0])
        if DEBUG_MODE:
            print(f"Search returned {num_found} results")
        
        if results["distances"] and results["distances"][0]:
            min_distance = min(results["distances"][0])
            if DEBUG_MODE:
                print(f"Closest match distance: {min_distance:.4f}")
            # Relaxed threshold from 1.2 to 1.4 to be more inclusive
            has_relevant_results = min_distance < 1.4
        else:
            has_relevant_results = True
    else:
        if DEBUG_MODE:
            print("WARNING: Search returned NO results (collection might be empty)")
    
    if not has_relevant_results:
        if DEBUG_MODE:
            print(f"WARNING: No highly relevant context found (min distance: {min_distance})")
            print(f"Attempting to answer using general cybersecurity knowledge...")
        return "No specific Cyberfortress documentation found for this query. Use general cybersecurity knowledge to answer.", set(), []
    
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
    
    # Debug info
    if DEBUG_MODE:
        if context_list:
            print(f"\nFound {len(context_list)} relevant documents")
            if sources:
                print(f"Sources: {', '.join(sources)}")
            
            # Preview context
            print(f"\nContext Preview (first 300 chars):")
            print("-" * 60)
            preview = context_text[:300] + "..." if len(context_text) > 300 else context_text
            print(preview)
            print("-" * 60)
        else:
            print(f"\nUsing general knowledge (no relevant context)")
    
    return context_text, sources, context_list


def _anonymize_context(context_text: str) -> str:
    """
    Anonymize sensitive information in context
    
    Returns:
        Anonymized context text
    """
    if DEBUG_ANONYMIZATION:
        print("\n" + "="*80)
        print("ANONYMIZATION DEBUG - CONTEXT BEFORE:")
        print("="*80)
        preview = context_text[:500] + "..." if len(context_text) > 500 else context_text
        print(preview)
        print("\n" + "="*80)
    
    context_text_anonymized = anonymize_text(context_text)
    
    ip_count = len(re.findall(r'TKN-IP-[a-f0-9]+', context_text_anonymized))
    host_count = len(re.findall(r'HOST-[a-f0-9]+', context_text_anonymized))
    if DEBUG_MODE:
        print(f"Anonymization: {ip_count} IPs, {host_count} hostnames protected")
    
    if DEBUG_ANONYMIZATION:
        print("\n" + "="*80)
        print("ANONYMIZATION DEBUG - CONTEXT AFTER (sent to OpenAI):")
        print("="*80)
        preview = context_text_anonymized[:500] + "..." if len(context_text_anonymized) > 500 else context_text_anonymized
        print(preview)
        print("\n" + "="*80)
        print("\nWARNING: NO REAL IPs OR DEVICE NAMES IN ABOVE TEXT - All replaced with tokens!")
        print("="*80)
    
    return context_text_anonymized


def _build_user_input(context_text_anonymized: str, query: str) -> str:
    """
    Build user input for API call using PromptBuilder
    """
    # Get user input template from PromptBuilder
    user_prompt_template = prompt_builder.build_user_input_prompt()
    
    # Format with context and query
    return user_prompt_template.format(
        context=context_text_anonymized,
        query=query
    )


def _call_openai_api(system_instructions: str, user_input: str, context_text_anonymized: str, query: str) -> tuple[str, float]:
    """
    Call OpenAI API and return response
    
    Returns:
        Tuple of (answer_text, actual_cost)
    """
    # Estimate cost
    estimated_prompt_tokens = len(context_text_anonymized) // 3 + len(query) // 3
    estimated_completion_tokens = 500
    estimated_cost = (estimated_prompt_tokens / 1_000_000) * INPUT_PRICE_PER_1M + \
                    (estimated_completion_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
    
    if not usage_tracker.check_daily_cost(estimated_cost):
        raise ValueError("ERROR: Daily cost limit reached. Please try again tomorrow.")
    
    # API call
    response = client.responses.create(
        model=CHAT_MODEL,
        instructions=system_instructions,
        input=user_input
    )
    
    # Extract token usage
    usage = response.usage
    actual_cost = 0.0
    if usage:
        input_tokens = getattr(usage, 'input_tokens', 0)
        output_tokens = getattr(usage, 'output_tokens', 0)
        total_tokens = getattr(usage, 'total_tokens', input_tokens + output_tokens)
        
        if DEBUG_MODE:
            print(f"\nToken Usage:")
            print(f"   - Input tokens: {input_tokens}")
            print(f"   - Output tokens: {output_tokens}")
            print(f"   - Total tokens: {total_tokens}")
        
        input_cost = (input_tokens / 1_000_000) * INPUT_PRICE_PER_1M
        output_cost = (output_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
        actual_cost = input_cost + output_cost
        
        if DEBUG_MODE:
            print(f"   - Estimated cost: ${actual_cost:.6f}")
        
        usage_tracker.record_call(actual_cost)
        
        if DEBUG_MODE:
            usage_stats = usage_tracker.get_stats()
            cache_stats = response_cache.get_stats()
            print(f"\nToday's Usage:")
            print(f"   - Total cost: ${usage_stats['daily_cost']:.4f} / ${MAX_DAILY_COST}")
            print(f"   - Calls in last minute: {usage_stats['calls_last_minute']} / {MAX_CALLS_PER_MINUTE}")
            print(f"   - Cache entries: {cache_stats['cache_size']}")
    
    answer_with_tokens = response.output_text or "No answer generated"
    
    if DEBUG_ANONYMIZATION:
        print("\n" + "="*80)
        print("AI RESPONSE (with anonymized tokens):")
        print("="*80)
        print(answer_with_tokens)
        print("\n" + "="*80)
    
    return answer_with_tokens, actual_cost


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
    print(f"\nQuestion: {query}")
    
    # Check rate limit
    if not usage_tracker.check_rate_limit():
        return "ERROR: Rate limit exceeded. Please wait a moment before trying again."
    
    # Search and build context
    context_text, sources, context_list = _search_and_build_context(collection, query, n_results, filter_metadata)
    
    # Check cache
    context_hash = hashlib.sha256(context_text.encode()).hexdigest()
    cache_key = response_cache.get_cache_key(query, context_hash)
    cached_response = response_cache.get(cache_key)
    
    if cached_response:
        return cached_response
    
    # Anonymize context
    context_text_anonymized = _anonymize_context(context_text)
    
    # Build API request
    system_instructions = prompt_builder.build_rag_prompt()
    user_input = _build_user_input(context_text_anonymized, query)
    
    # Call API with error handling
    try:
        answer_with_tokens, actual_cost = _call_openai_api(
            system_instructions, 
            user_input, 
            context_text_anonymized, 
            query
        )
        
        # De-anonymize response
        answer = deanonymize_text(answer_with_tokens)
        
        if DEBUG_ANONYMIZATION:
            print("\n" + "="*80)
            print("FINAL ANSWER (de-anonymized for user):")
            print("="*80)
            print(answer)
            print("\n" + "="*80)
        
        # Add source citations
        if sources:
            answer += f"\n\nSources: {', '.join(sorted(sources))}"
        
        # Cache the response
        response_cache.set(cache_key, answer)
        
        return answer
        
    except RateLimitError as e:
        error_msg = f"Rate limit exceeded. Please try again later. (Request ID: {getattr(e, 'request_id', 'N/A')})"
        print(f"\nERROR: {error_msg}")
        return error_msg
        
    except APIConnectionError as e:
        error_msg = f"Connection error: {str(e)}. Please check your internet connection."
        print(f"\nERROR: {error_msg}")
        return error_msg
        
    except APIError as e:
        error_msg = f"OpenAI API error: {str(e)} (Request ID: {getattr(e, 'request_id', 'N/A')})"
        print(f"\nERROR: {error_msg}")
        return error_msg
