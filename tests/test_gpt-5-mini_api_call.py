"""
Cyberfortress SOC RAG Assistant - Test GPT-5-mini API Call
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')

# Add project root and app directory to path
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'app'))

# Import after path setup
from app.core.database import initialize_database
from app.core.ingestion import ingest_data
from app.core.query import ask


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    # Check if .env file exists and has OPENAI_API_KEY
    env_file = project_root / '.env'
    if not env_file.exists():
        print("Error: .env file not found!")
        print(f"   Please create a .env file in: {project_root}")
        print("   Add your OpenAI API key: OPENAI_API_KEY=your-key-here")
        sys.exit(1)
    
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY not found in .env file!")
        print("   Please add your OpenAI API key to .env file")
        sys.exit(1)
    
    try:
        # Initialize database
        print("Initializing database...")
        collection = initialize_database()
        
        # Run data ingestion (only when updates needed)
        print("\nStarting data ingestion...")
        ingest_data(collection)
        
        print("\n" + "="*80)
        print("Cyberfortress SOC RAG Assistant - GPT-5-mini Test")
        print("="*80)
        print("Example questions:")
        print("  - What is Suricata's management IP?")
        print("  - How does traffic flow from Internet to internal systems?")
        print("  - What interfaces does pfSense have?")
        print("  - What vulnerabilities does DVWA have?")
        print("  - Where does Elastic SIEM collect logs from?")
        print("  - List all devices in SOC Subnet")
        print("="*80 + "\n")
        
        # Chat loop
        while True:
            q = input("Enter question (or 'exit' to quit): ").strip()
            if q.lower() in ["exit", "quit", "q"]:
                print("\nGoodbye!")
                break
            if not q:
                continue
            
            try:
                answer = ask(collection, q)
                print(f"\nAnswer:\n{answer}\n")
            except Exception as e:
                print(f"\nError: {e}")
                import traceback
                traceback.print_exc()
                print()
                
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

