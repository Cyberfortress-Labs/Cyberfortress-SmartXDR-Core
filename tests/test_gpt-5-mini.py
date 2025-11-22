"""
Cyberfortress SOC RAG Assistant - Main Entry Point
"""
from database import initialize_database
from ingestion import ingest_data
from query import ask


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    # Initialize database
    collection = initialize_database()
    
    # Run data ingestion (only when updates needed)
    ingest_data(collection)
    
    print("\n" + "="*80)
    print("🤖 Cyberfortress SOC RAG Assistant")
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
        q = input("💬 Enter question (or 'exit' to quit): ").strip()
        if q.lower() in ["exit", "quit", "q"]:
            print("\n👋 Goodbye!")
            break
        if not q:
            continue
        
        try:
            answer = ask(collection, q)
            print(f"\n💡 Answer:\n{answer}\n")
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

