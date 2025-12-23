#!/usr/bin/env python3
"""
RAG Core Optimization Tests
Tests the new re-ranking, MMR, and threshold features
"""
import sys
import json
import time
# Ensure /app is in python path
if '/app' not in sys.path:
    sys.path.append('/app')
# Also add current directory for local testing
sys.path.append('/home/wanthinnn/Cyberfortress-SmartXDR-Core')


def test_config_values():
    """Test that config values are correctly loaded"""
    print("\n" + "="*60)
    print("TEST 1: Config Values")
    print("="*60)
    
    from app.config import (
        CROSS_ENCODER_MODEL, 
        STRICT_THRESHOLD, 
        FALLBACK_THRESHOLD,
        MAX_RERANK_CANDIDATES,
        MAX_CONTEXT_CHARS
    )
    
    print(f"CROSS_ENCODER_MODEL: {CROSS_ENCODER_MODEL}")
    print(f"STRICT_THRESHOLD: {STRICT_THRESHOLD}")
    print(f"FALLBACK_THRESHOLD: {FALLBACK_THRESHOLD}")
    print(f"MAX_RERANK_CANDIDATES: {MAX_RERANK_CANDIDATES}")
    print(f"MAX_CONTEXT_CHARS: {MAX_CONTEXT_CHARS}")
    
    assert STRICT_THRESHOLD == 1.0, f"Expected STRICT_THRESHOLD=1.0, got {STRICT_THRESHOLD}"
    assert FALLBACK_THRESHOLD == 1.4, f"Expected FALLBACK_THRESHOLD=1.4, got {FALLBACK_THRESHOLD}"
    
    print("\n✅ Config values test PASSED")
    return True


def test_sentence_transformers_import():
    """Test that sentence-transformers is installed and working"""
    print("\n" + "="*60)
    print("TEST 2: Sentence Transformers Import")
    print("="*60)
    
    try:
        from sentence_transformers import CrossEncoder
        from app.config import CROSS_ENCODER_MODEL
        
        print(f"CrossEncoder imported successfully")
        print(f"Model to load: {CROSS_ENCODER_MODEL}")
        
        # Try loading the model (this downloads if not cached)
        print("  Loading cross-encoder model (may take a moment on first run)...")
        start = time.time()
        model = CrossEncoder(CROSS_ENCODER_MODEL, max_length=512)
        elapsed = time.time() - start
        print(f"Model loaded in {elapsed:.2f}s")
        
        # Test prediction
        test_pairs = [
            ("What is Suricata?", "Suricata is an IDS/IPS system."),
            ("What is Suricata?", "Python is a programming language.")
        ]
        scores = model.predict(test_pairs)
        print(f"Test scores: relevant={scores[0]:.3f}, irrelevant={scores[1]:.3f}")
        
        assert scores[0] > scores[1], "Relevant pair should score higher than irrelevant"
        
        print("\n✅ Sentence Transformers test PASSED")
        return True
        
    except ImportError as e:
        print(f"⚠️ sentence-transformers not installed: {e}")
        print("   This is optional - fallback to distance-based ranking will be used")
        return True  # Not a failure, just optional


def test_rag_service_methods():
    """Test that RAG service methods exist and work"""
    print("\n" + "="*60)
    print("TEST 3: RAG Service Methods")
    print("="*60)
    
    from app.rag.service import RAGService
    
    service = RAGService()
    
    # Check new methods exist
    methods = [
        '_filter_by_threshold',
        '_rerank_documents', 
        '_apply_mmr',
        '_text_overlap'
    ]
    
    for method in methods:
        assert hasattr(service, method), f"Missing method: {method}"
        print(f"Method exists: {method}")
    
    # Test _text_overlap
    overlap = service._text_overlap(
        "Suricata is an IDS IPS system for network security",
        "Suricata IDS provides network intrusion detection"
    )
    print(f"_text_overlap returned: {overlap:.3f}")
    assert 0 <= overlap <= 1, "Overlap should be between 0 and 1"
    
    print("\n✅ RAG Service methods test PASSED")
    return True


def test_cache_fix():
    """Test that cache bug is fixed"""
    print("\n" + "="*60)
    print("TEST 4: Cache Bug Fix")
    print("="*60)
    
    from app.utils.cache import ResponseCache
    
    cache = ResponseCache(ttl=1, enabled=True, use_semantic_cache=False)
    
    # Add some entries
    cache.set("test_key_1", "response_1", "query 1")
    cache.set("test_key_2", "response_2", "query 2")
    
    print(f"Added 2 cache entries")
    print(f"Cache size: {len(cache._local_cache)}")
    
    # Wait for TTL to expire
    print("  Waiting 2 seconds for TTL to expire...")
    time.sleep(2)
    
    # This should not crash (was using undefined 'cache_key' before fix)
    try:
        cache.clear_expired()
        print(f"clear_expired() executed without error")
        print(f"Cache size after cleanup: {len(cache._local_cache)}")
    except NameError as e:
        print(f"❌ Bug not fixed! Error: {e}")
        return False
    
    print("\n✅ Cache bug fix test PASSED")
    return True


def test_build_context_with_reranking():
    """Test build_context_from_query with new features"""
    print("\n" + "="*60)
    print("TEST 5: Build Context with Re-ranking")
    print("="*60)
    
    from app.rag.service import RAGService
    
    service = RAGService()
    
    # Get document count first
    stats = service.get_stats()
    doc_count = stats.get('repository', {}).get('total_documents', 0)
    print(f"Knowledge base has {doc_count} documents")
    
    if doc_count == 0:
        print("⚠️ No documents in knowledge base - skipping query test")
        return True
    
    # Test query
    test_query = "What is Suricata?"
    print(f"  Testing query: '{test_query}'")
    
    start = time.time()
    context, sources = service.build_context_from_query(
        test_query,
        top_k=5,
        use_reranking=True
    )
    elapsed = time.time() - start
    
    print(f"Query completed in {elapsed:.2f}s")
    print(f"Context length: {len(context)} chars")
    print(f"Sources: {sources[:3]}...")
    
    # Check quality indicator is present
    assert "[Context Quality:" in context, "Missing quality indicator"
    print(f"Quality indicator present in context")
    
    # Check context respects MAX_CONTEXT_CHARS
    from app.config import MAX_CONTEXT_CHARS
    # Allow some buffer for truncation message
    assert len(context) <= MAX_CONTEXT_CHARS + 200, f"Context too long: {len(context)}"
    print(f"Context respects MAX_CONTEXT_CHARS limit")
    
    print("\n✅ Build context test PASSED")
    return True


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  RAG CORE OPTIMIZATION TESTS")
    print("="*60)
    
    tests = [
        ("Config Values", test_config_values),
        ("Sentence Transformers", test_sentence_transformers_import),
        ("RAG Service Methods", test_rag_service_methods),
        ("Cache Bug Fix", test_cache_fix),
        ("Build Context", test_build_context_with_reranking),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ {name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("  TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, p in results:
        status = "✅ PASS" if p else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    print("="*60)
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
