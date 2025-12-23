"""
RAG query processing with token usage tracking
Using LangChain's ChatOpenAI for better error handling and token tracking
"""
import os
import re
import hashlib
import time
import json
from typing import Optional, Dict, Any, List, cast
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI
from langchain.callbacks import get_openai_callback
from langchain_core.messages import SystemMessage, HumanMessage
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
    SEMANTIC_CACHE_ENABLED,
    DEBUG_MODE
)
from app.services.prompt_builder_service import PromptBuilder
from app.utils.rate_limit import APIUsageTracker
from app.utils.cache import ResponseCache
from app.utils.logger import query_logger as logger

# Setup logger

# Load environment variables
load_dotenv()

# Initialize LangChain ChatOpenAI with proper configuration
llm = ChatOpenAI(
    model=CHAT_MODEL,
    api_key=os.environ.get("OPENAI_API_KEY"),
    timeout=OPENAI_TIMEOUT,
    max_retries=OPENAI_MAX_RETRIES,
    temperature=0,  # Deterministic for RAG
)

# Initialize PromptBuilder for system prompts (using RAG-optimized prompt)
prompt_builder = PromptBuilder(prompt_file='rag_system.json')

# Initialize API usage tracker and cache
usage_tracker = APIUsageTracker(
    max_calls_per_minute=MAX_CALLS_PER_MINUTE,
    max_daily_cost=MAX_DAILY_COST
)
response_cache = ResponseCache(ttl=CACHE_TTL, enabled=CACHE_ENABLED, use_semantic_cache=SEMANTIC_CACHE_ENABLED)

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
            logger.debug(f"Search returned {num_found} results")
        
        if results["distances"] and results["distances"][0]:
            min_distance = min(results["distances"][0])
            if DEBUG_MODE:
                logger.debug(f"Closest match distance: {min_distance:.4f}")
            # Relaxed threshold from 1.4 to 1.7 to be more inclusive
            has_relevant_results = min_distance < 1.7
        else:
            has_relevant_results = True
    else:
        if DEBUG_MODE:
            logger.warning("Search returned NO results (collection might be empty)")
    
    if not has_relevant_results:
        if DEBUG_MODE:
            logger.warning(f"No highly relevant context found (min distance: {min_distance})")
            logger.info("Attempting to answer using general cybersecurity knowledge...")
        return "No specific Cyberfortress documentation found for this query. Use general cybersecurity knowledge to answer.", set(), []
    
    # Build context from results
    context_list = results["documents"][0]
    metadatas_list = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []
    
    context_parts = []
    sources = set()
    
    for idx, (doc, meta, dist) in enumerate(zip(context_list, metadatas_list, distances)):
        if dist < 1.7:
            context_parts.append(f"[Document {idx + 1}]\n{doc}")
            if meta and "source" in meta:
                sources.add(meta["source"])
    
    context_text = "\n\n---\n\n".join(context_parts) if context_parts else "Limited relevant context found."
    
    # Debug info
    if DEBUG_MODE:
        if context_list:
            logger.debug(f"Found {len(context_list)} relevant documents")
            if sources:
                logger.debug(f"Sources: {', '.join(sources)}")
            
            # Preview context
            logger.debug(f"Context Preview (first 300 chars):")
            preview = context_text[:300] + "..." if len(context_text) > 300 else context_text
            logger.debug(preview)
        else:
            logger.debug("Using general knowledge (no relevant context)")
    
    return context_text, sources, context_list

def _build_user_input(context_text: str, query: str) -> str:
    """
    Build user input for API call using PromptBuilder
    """
    # Get user input template from PromptBuilder
    user_prompt_template = prompt_builder.build_user_input_prompt()
    
    # Format with context and query
    return user_prompt_template.format(
        context=context_text,
        query=query
    )

def _call_openai_api(system_instructions: str, user_input: str, context_text: str, query: str) -> tuple[str, float]:
    """
    Call OpenAI API using LangChain ChatOpenAI and return response
    
    Benefits of LangChain:
    - Built-in token tracking via get_openai_callback()
    - Automatic retry logic with exponential backoff
    - Better error handling with specific exception types
    - Streaming support (can be enabled if needed)
    
    Returns:
        Tuple of (answer_text, actual_cost)
    """
    # Estimate cost for rate limiting check
    estimated_prompt_tokens = len(context_text) // 3 + len(query) // 3
    estimated_completion_tokens = 500
    estimated_cost = (estimated_prompt_tokens / 1_000_000) * INPUT_PRICE_PER_1M + \
                    (estimated_completion_tokens / 1_000_000) * OUTPUT_PRICE_PER_1M
    
    if not usage_tracker.check_daily_cost(estimated_cost):
        raise ValueError("ERROR: Daily cost limit reached. Please try again tomorrow.")
    
    # Build messages for LangChain
    messages = [
        SystemMessage(content=system_instructions),
        HumanMessage(content=user_input)
    ]
    
    # Call LLM with token tracking callback
    with get_openai_callback() as cb:
        response = llm.invoke(messages)
    
    # Extract answer
    answer_text = response.content if response.content else "No answer generated"
    
    # Calculate actual cost from callback
    actual_cost = cb.total_cost
    
    if DEBUG_MODE:
        logger.debug(f"\nToken Usage (via LangChain callback):")
        logger.debug(f"   - Input tokens: {cb.prompt_tokens}")
        logger.debug(f"   - Output tokens: {cb.completion_tokens}")
        logger.debug(f"   - Total tokens: {cb.total_tokens}")
        logger.debug(f"   - Actual cost: ${actual_cost:.6f}")
    
    # Record usage in tracker
    usage_tracker.record_call(actual_cost)
    
    if DEBUG_MODE:
        usage_stats = usage_tracker.get_stats()
        cache_stats = response_cache.get_stats()
        logger.debug(f"\nToday's Usage:")
        logger.debug(f"   - Total cost: ${usage_stats['daily_cost']:.4f} / ${MAX_DAILY_COST}")
        logger.debug(f"   - Calls in last minute: {usage_stats['calls_last_minute']} / {MAX_CALLS_PER_MINUTE}")
        logger.debug(f"   - Cache entries: {cache_stats['cache_size']}")
    
    return answer_text, actual_cost

def ask(collection, query: str, n_results: int = DEFAULT_RESULTS, filter_metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Search and answer questions with enhancements:
    - Increased results for more context
    - Metadata filtering support
    - Source citations
    - Token usage tracking via LangChain callbacks
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
    logger.info(f"Question: {query}")
    
    # Check rate limit
    if not usage_tracker.check_rate_limit():
        return "ERROR: Rate limit exceeded. Please wait a moment before trying again."
    
    # Search and build context
    context_text, sources, context_list = _search_and_build_context(collection, query, n_results, filter_metadata)
    
    # Check cache - use query normalization only (ignore context_hash)
    # This allows queries with different contexts but same semantic meaning to hit cache
    cache_key = response_cache.get_cache_key(query, "")  # Empty context_hash to focus on query similarity
    cached_response = response_cache.get(cache_key, query)  # Pass query for semantic matching
    
    if cached_response:
        return cached_response
    
    # Build API request
    system_instructions = prompt_builder.build_rag_prompt()
    user_input = _build_user_input(context_text, query)
    
    # Call API with error handling (LangChain handles retries automatically)
    try:
        answer_with_tokens, actual_cost = _call_openai_api(
            system_instructions, 
            user_input, 
            context_text, 
            query
        )
        
        # Use response as-is
        answer = answer_with_tokens
        
        # Add source citations
        if sources:
            answer += f"\n\nSources: {', '.join(sorted(sources))}"
        
        # Cache the response (with query for semantic matching)
        response_cache.set(cache_key, answer, query)
        
        return answer
        
    except Exception as e:
        error_msg = f"Error processing query: {str(e)}"
        logger.error(f"ERROR: {error_msg}")
        return error_msg
