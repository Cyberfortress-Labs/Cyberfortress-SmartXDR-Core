
# To run this code you need to install the following dependencies:
# pip install google-genai python-dotenv

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import time

# Load .env file from project root
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')

# Add project root to path
sys.path.insert(0, str(project_root))

from google import genai
from google.genai import types
from app.services.prompt_builder import get_system_prompt


def test_explicit_caching():
    """Test explicit context caching with Gemini API"""
    
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    # Build system prompt (JSON format for better LLM parsing)
    system_prompt = get_system_prompt(include_full_context=False, format='text')
    
    print(f"[INFO] System prompt loaded: {len(system_prompt)} characters")
    print(f"[INFO] Estimated tokens: ~{len(system_prompt) // 3} tokens\n")
    
    model_name = 'gemini-2.5-flash'
    
    # Create a cache with system instruction
    # TTL: 3600s = 1 hour (you can adjust based on your needs)
    print("[STEP 1] Creating cache...")
    cache = client.caches.create(
        model=model_name,
        config=types.CreateCachedContentConfig(
            display_name='smartxdr-system-prompt',  # Used to identify the cache
            system_instruction=system_prompt,
            ttl='3600s',  # Cache for 1 hour
        )
    )
    
    print(f"[SUCCESS] Cache created: {cache.name}")
    print(f"[INFO] Cache metadata:")
    print(f"  - Model: {cache.model}")
    print(f"  - Display name: {cache.display_name}")
    print(f"  - Expire time: {cache.expire_time}")
    print(f"  - Create time: {cache.create_time}\n")
    
    # Request 1 - First request using cached content
    print("=" * 80)
    print("[REQUEST 1] Asking about Suricata interfaces (using cached prompt)")
    print("=" * 80)
    
    response1 = client.models.generate_content(
        model=model_name,
        contents='Suricata có những interface nào và mỗi interface có vai trò gì?',
        config=types.GenerateContentConfig(
            cached_content=cache.name  # Reference the cache by name
        )
    )
    
    print(f"\n[USAGE METADATA - Request 1]")
    print(f"  - Prompt tokens: {response1.usage_metadata.prompt_token_count}")
    print(f"  - Cached tokens: {response1.usage_metadata.cached_content_token_count}")
    print(f"  - Output tokens: {response1.usage_metadata.candidates_token_count}")
    print(f"  - Total tokens: {response1.usage_metadata.total_token_count}")
    
    print(f"\n[RESPONSE 1]")
    print(response1.text)
    
    # Small delay between requests
    time.sleep(1)
    
    # Request 2 - Second request using the same cached content
    print("\n" + "=" * 80)
    print("[REQUEST 2] Asking about Zeek monitoring (using SAME cached prompt)")
    print("=" * 80)
    
    response2 = client.models.generate_content(
        model=model_name,
        contents='Zeek monitor traffic như thế nào? Nó khác gì với Suricata?',
        config=types.GenerateContentConfig(
            cached_content=cache.name  # Reuse the same cache
        )
    )
    
    print(f"\n[USAGE METADATA - Request 2]")
    print(f"  - Prompt tokens: {response2.usage_metadata.prompt_token_count}")
    print(f"  - Cached tokens: {response2.usage_metadata.cached_content_token_count}")
    print(f"  - Output tokens: {response2.usage_metadata.candidates_token_count}")
    print(f"  - Total tokens: {response2.usage_metadata.total_token_count}")
    
    print(f"\n[RESPONSE 2]")
    print(response2.text)
    
    # Calculate savings
    print("\n" + "=" * 80)
    print("[CACHE SAVINGS ANALYSIS]")
    print("=" * 80)
    
    total_prompt_tokens = response1.usage_metadata.prompt_token_count + response2.usage_metadata.prompt_token_count
    total_cached_tokens = response1.usage_metadata.cached_content_token_count + response2.usage_metadata.cached_content_token_count
    
    # Pricing (as of 2025, check ai.google.dev/pricing for updates)
    # Input tokens: $0.075 / 1M tokens
    # Cached tokens (storage): $0.01875 / 1M tokens (75% discount)
    # Cached tokens (usage): $0.01875 / 1M tokens (75% discount)
    
    input_cost = (total_prompt_tokens / 1_000_000) * 0.075
    cache_cost = (total_cached_tokens / 1_000_000) * 0.01875
    
    print(f"Total prompt tokens sent: {total_prompt_tokens}")
    print(f"Total cached tokens reused: {total_cached_tokens}")
    print(f"Cache hit rate: {(total_cached_tokens / (total_prompt_tokens + total_cached_tokens) * 100):.1f}%")
    print(f"\nEstimated cost:")
    print(f"  - Input tokens cost: ${input_cost:.6f}")
    print(f"  - Cached tokens cost: ${cache_cost:.6f}")
    print(f"  - Total cost: ${(input_cost + cache_cost):.6f}")
    print(f"  - Savings vs no cache: ~{((1 - cache_cost / input_cost) * 100):.1f}%")
    
    # Optional: Delete the cache when done
    print("\n" + "=" * 80)
    print("[CLEANUP] Do you want to delete the cache? (y/n)")
    # client.caches.delete(cache.name)
    # print(f"[SUCCESS] Cache deleted: {cache.name}")


def list_all_caches():
    """List all existing caches"""
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )
    
    print("\n[LISTING ALL CACHES]")
    print("=" * 80)
    
    caches = list(client.caches.list())
    
    if not caches:
        print("No caches found.")
    else:
        for i, cache in enumerate(caches, 1):
            print(f"\nCache #{i}:")
            print(f"  - Name: {cache.name}")
            print(f"  - Model: {cache.model}")
            print(f"  - Display name: {cache.display_name}")
            print(f"  - Expire time: {cache.expire_time}")
            print(f"  - Create time: {cache.create_time}")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("GEMINI EXPLICIT CONTEXT CACHING TEST")
    print("=" * 80 + "\n")
    
    # Test explicit caching
    test_explicit_caching()
    
    # List all caches
    list_all_caches()
    
    print("\n" + "=" * 80)
    print("TEST COMPLETED")
    print("=" * 80)