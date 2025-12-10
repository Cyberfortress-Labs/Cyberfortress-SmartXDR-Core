import sys
sys.path.insert(0, '.')
import chromadb
from app.config import CHROMA_DB_PATH

client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
collection = client.get_collection('knowledge_base')

print(f"Total documents: {collection.count()}")
print()

query = "IP 192.168.100.128 là của máy nào?"
print(f"Query: {query}")
print("=" * 70)

results = collection.query(
    query_texts=[query],
    n_results=10
)

if results['documents'] and results['documents'][0]:
    print(f"Found {len(results['documents'][0])} results")
    print()
    
    for i, (doc, meta, dist) in enumerate(zip(
        results['documents'][0],
        results['metadatas'][0],
        results['distances'][0]
    )):
        print(f"[{i+1}] Distance: {dist:.4f}")
        print(f"    Source: {meta.get('source', 'unknown')}")
        print(f"    Category: {meta.get('category', 'unknown')}")
        
        if '192.168.100.128' in doc:
            print(f"    ✓✓✓ CONTAINS 192.168.100.128 ✓✓✓")
        
        print(f"    Content: {doc[:150]}...")
        print()
else:
    print("No results found!")
