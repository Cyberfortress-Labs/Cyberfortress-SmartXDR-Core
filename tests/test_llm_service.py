from app.services.llm_service import LLMService

llm = LLMService()  # Singleton

# RAG query
result = llm.ask_rag(collection, "What is X?")

# IntelOwl analysis
result = llm.explain_intelowl_results(ioc_value, raw_results)

# Stats
stats = llm.get_stats()