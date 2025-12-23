from app.utils.logger import pdf_logger as logger
"""
PDF Processing Module for RAG

Extracts text from PDF files using PyMuPDF (fitz).
Optimized for memory efficiency with streaming page-by-page processing.

Key features:
- Extract full text from PDF (concatenated)
- Track page numbers for citation metadata
- Handle corrupted/encrypted PDFs gracefully
- Memory-efficient streaming for large files
"""
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

def extract_text_from_pdf(file_path: str | Path) -> Optional[str]:
    """
    Extract all text from a PDF file.
    
    Memory-efficient: processes page-by-page and concatenates.
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Full text content or None if extraction fails
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install pymupdf")
        return None
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"PDF file not found: {file_path}")
        return None
    
    if not file_path.suffix.lower() == '.pdf':
        logger.warning(f"File is not a PDF: {file_path}")
        return None
    
    try:
        # Open PDF document
        doc = fitz.open(str(file_path))
        
        # Check if encrypted
        if doc.is_encrypted:
            logger.warning(f"PDF is encrypted: {file_path}")
            # Try to open without password (some PDFs allow this)
            if not doc.authenticate(""):
                logger.error(f"Cannot decrypt PDF: {file_path}")
                doc.close()
                return None
        
        # Extract text page by page (memory efficient)
        text_parts = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(page_text)
        
        doc.close()
        
        # Join with double newlines to preserve page separation
        full_text = "\n\n".join(text_parts)
        
        if not full_text.strip():
            logger.warning(f"No text extracted from PDF: {file_path}")
            return None
        
        logger.info(f"Extracted {len(full_text)} chars from {len(text_parts)} pages: {file_path.name}")
        return full_text
        
    except Exception as e:
        logger.error(f"Error extracting text from PDF {file_path}: {e}")
        return None

def extract_text_with_page_info(file_path: str | Path) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Extract text from PDF with page position information for citation.
    
    Useful for tracking which page content came from, while still
    using character-based chunking (not page-based).
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Tuple of (full_text, page_info) where page_info is a list of:
        [{"page": 1, "start_char": 0, "end_char": 500}, ...]
        Returns None if extraction fails.
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF not installed. Run: pip install pymupdf")
        return None
    
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"PDF file not found: {file_path}")
        return None
    
    try:
        doc = fitz.open(str(file_path))
        
        if doc.is_encrypted and not doc.authenticate(""):
            logger.error(f"Cannot decrypt PDF: {file_path}")
            doc.close()
            return None
        
        text_parts = []
        page_info = []
        current_pos = 0
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text")
            
            if page_text.strip():
                # Add page separator if not first page
                if text_parts:
                    text_parts.append("\n\n")
                    current_pos += 2
                
                start_char = current_pos
                text_parts.append(page_text)
                current_pos += len(page_text)
                
                page_info.append({
                    "page": page_num + 1,  # 1-indexed
                    "start_char": start_char,
                    "end_char": current_pos
                })
        
        doc.close()
        
        full_text = "".join(text_parts)
        
        if not full_text.strip():
            logger.warning(f"No text extracted from PDF: {file_path}")
            return None
        
        logger.info(f"Extracted {len(full_text)} chars from {len(page_info)} pages with position info")
        return (full_text, page_info)
        
    except Exception as e:
        logger.error(f"Error extracting text with page info from PDF {file_path}: {e}")
        return None

def get_page_for_position(char_position: int, page_info: List[Dict[str, Any]]) -> Optional[int]:
    """
    Get the page number for a character position.
    
    Args:
        char_position: Character position in the full text
        page_info: Page info from extract_text_with_page_info()
        
    Returns:
        Page number (1-indexed) or None if not found
    """
    for info in page_info:
        if info["start_char"] <= char_position < info["end_char"]:
            return info["page"]
    return None

def get_pdf_metadata(file_path: str | Path) -> Optional[Dict[str, Any]]:
    """
    Extract PDF metadata (title, author, creation date, etc.)
    
    Args:
        file_path: Path to the PDF file
        
    Returns:
        Dictionary with PDF metadata or None if extraction fails
    """
    try:
        import fitz
    except ImportError:
        return None
    
    file_path = Path(file_path)
    
    try:
        doc = fitz.open(str(file_path))
        
        metadata = {
            "page_count": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "creator": doc.metadata.get("creator", ""),
            "creation_date": doc.metadata.get("creationDate", ""),
            "modification_date": doc.metadata.get("modDate", ""),
        }
        
        doc.close()
        return metadata
        
    except Exception as e:
        logger.error(f"Error getting PDF metadata: {e}")
        return None
