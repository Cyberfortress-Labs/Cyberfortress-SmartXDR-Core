#!/usr/bin/env python3
"""
Script to update logging imports across the codebase
Replaces: import logging + logging.getLogger('name')
With: from app.utils.logger import <module>_logger as logger
"""
import re
import os

# Mapping of logger name patterns to import statements
LOGGER_MAPPING = {
    # RAG module
    'smartxdr.rag.repository': 'from app.utils.logger import rag_repository_logger as logger',
    'smartxdr.rag.service': 'from app.utils.logger import rag_service_logger as logger', 
    'smartxdr.rag.monitoring': 'from app.utils.logger import rag_monitoring_logger as logger',
    
    # Core module
    'smartxdr.database': 'from app.utils.logger import database_logger as logger',
    'smartxdr.chunking': 'from app.utils.logger import chunking_logger as logger',
    'smartxdr.ingestion': 'from app.utils.logger import ingestion_logger as logger',
    'smartxdr.query': 'from app.utils.logger import query_logger as logger',
    'smartxdr.core.pdf_processor': 'from app.utils.logger import pdf_logger as logger',
    'smartxdr.openai': 'from app.utils.logger import openai_logger as logger',
    
    # Routes
    'smartxdr.ai': 'from app.utils.logger import ai_route_logger as logger',
    'smartxdr.rag.routes': 'from app.utils.logger import rag_route_logger as logger',
    
    # Services  
    'smartxdr.conversation': 'from app.utils.logger import conversation_logger as logger',
    'smartxdr.iris': 'from app.utils.logger import iris_logger as logger',
    'smartxdr.enrich': 'from app.utils.logger import enrich_logger as logger',
    
    # Utils
    'smartxdr.cache': 'from app.utils.logger import cache_logger as logger',
    'smartxdr.redis': 'from app.utils.logger import redis_logger as logger',
    
    # Generic fallbacks
    '__name__': 'from app.utils.logger import get_logger; logger = get_logger(__name__)',
}

FILES_TO_UPDATE = [
    'app/rag/repository.py',
    'app/rag/service.py',
    'app/rag/monitoring.py',
    'app/core/database.py',
    'app/core/chunking.py',
    'app/core/ingestion.py',
    'app/core/query.py',
    'app/core/pdf_processor.py',
    'app/core/openai_client.py',
    'app/routes/ai.py',
    'app/routes/rag.py',
    'app/services/conversation_memory.py',
    'app/services/iris_service.py',
    'app/services/enrich_service.py',
    'app/utils/cache.py',
    'app/utils/redis_client.py',
]

def update_file(filepath):
    """Update a single file to use centralized logger"""
    if not os.path.exists(filepath):
        print(f"  SKIP: {filepath} not found")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Find the logger pattern: logger = logging.getLogger('name')
    match = re.search(r"logger\s*=\s*logging\.getLogger\(['\"]([^'\"]+)['\"]\)", content)
    if not match:
        # Try __name__ pattern
        match = re.search(r"logger\s*=\s*logging\.getLogger\(__name__\)", content)
        if match:
            logger_name = '__name__'
        else:
            print(f"  SKIP: {filepath} - no logger pattern found")
            return False
    else:
        logger_name = match.group(1)
    
    # Get the import statement for this logger
    import_stmt = None
    for pattern, stmt in LOGGER_MAPPING.items():
        if pattern in logger_name or logger_name == pattern:
            import_stmt = stmt
            break
    
    if not import_stmt:
        print(f"  SKIP: {filepath} - no mapping for '{logger_name}'")
        return False
    
    # Remove 'import logging' line
    content = re.sub(r'^import logging\n', '', content, flags=re.MULTILINE)
    
    # Remove the old logger = logging.getLogger(...) line
    content = re.sub(r"^logger\s*=\s*logging\.getLogger\([^)]+\)\n", '', content, flags=re.MULTILINE)
    
    # Find the right place to add the import (after other imports)
    # Look for the last 'from app...' or 'import ...' line in the imports section
    lines = content.split('\n')
    insert_idx = 0
    
    for i, line in enumerate(lines):
        if line.startswith('from app.') or line.startswith('import '):
            insert_idx = i + 1
        elif line.strip() and not line.startswith('#') and not line.startswith('"""') and not line.startswith("'''"):
            if 'def ' in line or 'class ' in line:
                break
    
    # Insert the new import
    lines.insert(insert_idx, import_stmt)
    content = '\n'.join(lines)
    
    # Clean up any double blank lines
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  UPDATED: {filepath}")
        return True
    else:
        print(f"  NO CHANGE: {filepath}")
        return False

def main():
    print("Updating logging imports...")
    updated = 0
    for filepath in FILES_TO_UPDATE:
        if update_file(filepath):
            updated += 1
    print(f"\nDone! Updated {updated}/{len(FILES_TO_UPDATE)} files")

if __name__ == '__main__':
    main()
