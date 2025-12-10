"""
RAG (Retrieval-Augmented Generation) Module

Provides knowledge base management and semantic search capabilities.
"""

from app.rag.service import RAGService
from app.rag.repository import RAGRepository

__all__ = ['RAGService', 'RAGRepository']
