
import os
import sys
import logging
from dotenv import load_dotenv

# Ensure /app is in python path
if '/app' not in sys.path:
    sys.path.append('/app')
# Also add current directory for local testing
sys.path.append('/home/wanthinnn/Cyberfortress-SmartXDR-Core')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_similarity():
    query1 = "Kiểm tra IP 192.168.1.1"
    query2 = "Kiểm tra IP 192.168.1.20"
    
    logger.info(f"Checking similarity between:\n1. '{query1}'\n2. '{query2}'")
    
    try:
        from app.utils.cache import ResponseCache
        # Enable semantic cache
        cache = ResponseCache(enabled=True, use_semantic_cache=True)
        
        if not cache.use_semantic_cache:
            logger.error("Semantic cache is NOT enabled (likely missing langchain or openai key)")
            return

        logger.info("Generating embeddings...")
        emb1 = cache._get_embedding(query1)
        emb2 = cache._get_embedding(query2)
        
        if not emb1 or not emb2:
            logger.error("Failed to generate embeddings")
            return
            
        similarity = cache._cosine_similarity(emb1, emb2)
        logger.info(f"Similarity Score: {similarity:.4f}")
        logger.info(f"Threshold: {cache.similarity_threshold}")
        
        if similarity >= cache.similarity_threshold:
            logger.info("Result: WOULD HIT CACHE")
        else:
            logger.info("Result: MISS (Below Threshold)")
            
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Load env for OpenAI Key
    load_dotenv('/home/wanthinnn/Cyberfortress-SmartXDR-Core/.env')
    check_similarity()
