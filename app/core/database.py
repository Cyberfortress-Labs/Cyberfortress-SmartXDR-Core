"""
ChromaDB initialization and collection management

Uses RAGRepository as the single source of truth for ChromaDB client initialization.
This module provides backward compatibility for legacy code that expects a raw collection.
"""
from app.config import DB_PATH, COLLECTION_NAME
from app.utils.logger import database_logger as logger

def initialize_database():
    """
    Initialize ChromaDB and return collection.
    
    Uses RAGRepository internally to avoid duplicating ChromaDB client logic.
    Returns raw ChromaDB collection for backward compatibility with ingestion.py.
    
    Returns:
        chromadb.Collection: The ChromaDB collection instance
    """
    from app.rag.repository import RAGRepository
    
    # Create repository (handles Docker vs local client selection)
    repo = RAGRepository(
        persist_directory=DB_PATH,
        collection_name=COLLECTION_NAME
    )
    
    logger.info(f"Database initialized via RAGRepository: {COLLECTION_NAME}")
    
    # Return raw collection for backward compatibility
    return repo.collection

