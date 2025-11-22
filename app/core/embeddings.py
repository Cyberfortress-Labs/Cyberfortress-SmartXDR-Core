"""
OpenAI embedding function for ChromaDB
Following OpenAI Python SDK best practices
"""
import os
import chromadb
from openai import OpenAI
from config import EMBEDDING_MODEL, OPENAI_TIMEOUT, OPENAI_MAX_RETRIES
from dotenv import load_dotenv

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


class OpenAIEmbeddingFunction(chromadb.EmbeddingFunction):
    """
    Custom embedding function using OpenAI's text-embedding-3-small model
    
    Implements ChromaDB's EmbeddingFunction interface with OpenAI embeddings.
    Automatically handles retries and timeouts via configured client.
    """
    
    def __call__(self, input: list[str]) -> list[list[float]]:
        """
        Generate embeddings for input texts
        
        Args:
            input: List of texts to embed
            
        Returns:
            List of embedding vectors (list of floats)
        """
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=input
        )
        return [data.embedding for data in response.data]
