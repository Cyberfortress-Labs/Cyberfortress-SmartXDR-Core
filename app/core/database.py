"""
ChromaDB initialization and collection management
"""
import chromadb
from app.config import DB_PATH, COLLECTION_NAME
from app.core.embeddings import OpenAIEmbeddingFunction


def initialize_database():
    """Initialize ChromaDB with persistent storage and return collection"""
    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    openai_ef = OpenAIEmbeddingFunction()
    
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=openai_ef, 
        metadata={"hnsw:space": "cosine"}
    )
    
    return collection
