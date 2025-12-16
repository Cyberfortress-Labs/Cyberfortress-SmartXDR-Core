"""
OpenAI embedding function for ChromaDB
Uses shared OpenAI client with proper error handling
"""
import chromadb
from app.config import EMBEDDING_MODEL
from app.core.openai_client import get_openai_client


class OpenAIEmbeddingFunction(chromadb.EmbeddingFunction):
    """
    Custom embedding function using OpenAI's text-embedding-3-small model
    
    Implements ChromaDB's EmbeddingFunction interface with OpenAI embeddings.
    Uses shared client singleton for connection reuse.
    """
    
    def __call__(self, input: list[str]) -> list[list[float]]:
        """
        Generate embeddings for input texts
        
        Args:
            input: List of texts to embed
            
        Returns:
            List of embedding vectors (list of floats)
        """
        if not input:
            return []
        
        client = get_openai_client()
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=input
        )
        # Ensure we return Python lists, not numpy arrays
        return [list(data.embedding) for data in response.data]

