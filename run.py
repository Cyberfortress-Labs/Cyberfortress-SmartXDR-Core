"""
Cyberfortress SmartXDR Core - Flask Application Entry Point
"""
import os
from dotenv import load_dotenv
from app import create_app, get_collection
from app.config import PORT, HOST
from app.core.ingestion import ingest_data

# Load environment variables
load_dotenv()

# Create Flask app (this initializes the collection)
app = create_app()

if __name__ == '__main__':
    # Check API key
    if not os.getenv('OPENAI_API_KEY'):
        print("ERROR: OPENAI_API_KEY not found in .env file!")
        print("   Please add your OpenAI API key to .env file")
        exit(1)
    
    # Run data ingestion on startup
    print("Initializing data ingestion...")
    collection = get_collection()
    ingest_data(collection)
    print("Data ingestion completed.\n")
    
    # Run Flask app
    print("="*80)
    print("Cyberfortress SmartXDR Core - API Server")
    print("="*80)
    print("Endpoints:")
    print("  AI/RAG:")
    print("    - POST /api/ai/ask       - Ask LLM a question")
    print("    - GET  /api/ai/stats     - Get usage statistics")
    print("    - POST /api/ai/cache/clear - Clear response cache")
    print("  IOC Enrichment:")
    print("    - POST /api/enrich/explain_intelowl - Explain IntelOwl results with AI (single IOC)")
    print("    - POST /api/enrich/explain_case_iocs - Analyze all IOCs in a case with AI")
    print("  Health:")
    print("    - GET  /health           - Health check")
    print("="*80 + "\n")
    
    app.run(
        host=HOST,
        port=PORT,
        debug=True
    )
