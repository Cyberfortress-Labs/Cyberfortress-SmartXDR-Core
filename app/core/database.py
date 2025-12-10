"""
ChromaDB initialization and collection management
"""
import os
import chromadb
from app.config import DB_PATH, COLLECTION_NAME
from app.core.embeddings import OpenAIEmbeddingFunction
import logging

logger = logging.getLogger('smartxdr.database')


def initialize_database():
    """Initialize ChromaDB with Docker HttpClient or local PersistentClient"""
    openai_ef = OpenAIEmbeddingFunction()
    
    # Check if running in Docker environment
    chroma_host = os.getenv("CHROMA_HOST")
    chroma_port = os.getenv("CHROMA_PORT", "8000")
    
    if chroma_host:
        # Docker environment - use HttpClient
        logger.info(f"Connecting to ChromaDB service at {chroma_host}:{chroma_port}")
        try:
            chroma_client = chromadb.HttpClient(
                host=chroma_host,
                port=int(chroma_port)
            )
            logger.info("✓ Connected to ChromaDB service")
        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB service: {e}")
            logger.warning("Falling back to local PersistentClient")
            chroma_client = chromadb.PersistentClient(path=DB_PATH)
    else:
        # Local development - use PersistentClient
        logger.info(f"Using local ChromaDB at {DB_PATH}")
        chroma_client = chromadb.PersistentClient(path=DB_PATH)
    
    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=openai_ef, 
        metadata={"hnsw:space": "cosine"}
    )
    
    return collection
