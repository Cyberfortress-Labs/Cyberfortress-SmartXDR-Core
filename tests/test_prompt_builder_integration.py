"""
Test PromptBuilder Integration
Verify that PromptBuilder works correctly in query.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.prompt_builder_service import PromptBuilder

def test_prompt_builder():
    """Test basic PromptBuilder functionality"""
    print("=" * 80)
    print("Testing PromptBuilder Integration")
    print("=" * 80)
    
    # Test 1: Base system prompt (full version)
    print("\n1. BASE SYSTEM PROMPT (base_system.json - Full version):")
    print("-" * 80)
    builder_base = PromptBuilder(prompt_file='base_system.json')
    text_prompt = builder_base.build_system_prompt(
        include_full_context=False,
        format='text'
    )
    print(f"Length: {len(text_prompt)} characters (~{len(text_prompt)//4} tokens)")
    print("\nFirst 500 characters:")
    print(text_prompt[:500])
    print("...")
    
    # Test 2: RAG-optimized prompt
    print("\n\n2. RAG-OPTIMIZED PROMPT (rag_system.json - Lightweight):")
    print("-" * 80)
    builder_rag = PromptBuilder(prompt_file='rag_system.json')
    rag_prompt = builder_rag.build_rag_prompt()
    print(f"Length: {len(rag_prompt)} characters (~{len(rag_prompt)//4} tokens)")
    print("\nFull content:")
    print(rag_prompt)
    
    # Comparison
    print("\n\n3. TOKEN SAVINGS COMPARISON:")
    print("-" * 80)
    print(f"Base system prompt:     {len(text_prompt):,} chars (~{len(text_prompt)//4:,} tokens)")
    print(f"RAG-optimized prompt:   {len(rag_prompt):,} chars (~{len(rag_prompt)//4:,} tokens)")
    savings = ((len(text_prompt) - len(rag_prompt)) / len(text_prompt)) * 100
    print(f"Token savings:          {savings:.1f}%")
    print(f"Tokens saved per call:  ~{(len(text_prompt) - len(rag_prompt))//4:,} tokens")
    
    print("\n" + "=" * 80)
    print("PromptBuilder Integration Test Completed!")
    print("=" * 80)


if __name__ == "__main__":
    test_prompt_builder()
