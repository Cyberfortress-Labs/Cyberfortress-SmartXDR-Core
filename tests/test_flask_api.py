"""
Test Flask API - Ask LLM Endpoint
"""
import requests
import json

BASE_URL = "http://localhost:8080"

def test_ask_endpoint():
    """Test POST /api/ai/ask"""
    print("="*80)
    print("Test 1: Ask LLM a question")
    print("="*80)
    
    payload = {
        "query": "What is Suricata's management IP?",
        "n_results": 10
    }
    
    response = requests.post(
        f"{BASE_URL}/api/ai/ask",
        json=payload,
        headers={'Content-Type': 'application/json'}
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2))
    print()


def test_stats_endpoint():
    """Test GET /api/ai/stats"""
    print("="*80)
    print("Test 2: Get API statistics")
    print("="*80)
    
    response = requests.get(f"{BASE_URL}/api/ai/stats")
    
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2))
    print()


def test_cache_clear():
    """Test POST /api/ai/cache/clear"""
    print("="*80)
    print("Test 3: Clear cache")
    print("="*80)
    
    response = requests.post(f"{BASE_URL}/api/ai/cache/clear")
    
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2))
    print()


def test_health_check():
    """Test GET /health"""
    print("="*80)
    print("Test 4: Health check")
    print("="*80)
    
    response = requests.get(f"{BASE_URL}/health")
    
    print(f"Status Code: {response.status_code}")
    print(f"Response:")
    print(json.dumps(response.json(), indent=2))
    print()


def test_error_cases():
    """Test error handling"""
    print("="*80)
    print("Test 5: Error cases")
    print("="*80)
    
    # Missing query field
    print("\n5.1: Missing query field")
    response = requests.post(
        f"{BASE_URL}/api/ai/ask",
        json={},
        headers={'Content-Type': 'application/json'}
    )
    print(f"Status: {response.status_code}, Response: {response.json()}")
    
    # Empty query
    print("\n5.2: Empty query")
    response = requests.post(
        f"{BASE_URL}/api/ai/ask",
        json={"query": ""},
        headers={'Content-Type': 'application/json'}
    )
    print(f"Status: {response.status_code}, Response: {response.json()}")
    
    # Invalid n_results
    print("\n5.3: Invalid n_results")
    response = requests.post(
        f"{BASE_URL}/api/ai/ask",
        json={"query": "test", "n_results": 100},
        headers={'Content-Type': 'application/json'}
    )
    print(f"Status: {response.status_code}, Response: {response.json()}")
    print()


if __name__ == "__main__":
    try:
        print("\nCyberfortress SmartXDR Core - API Testing\n")
        
        # Run tests
        test_health_check()
        test_ask_endpoint()
        test_stats_endpoint()
        test_cache_clear()
        test_error_cases()
        
        print("="*80)
        print("All tests completed!")
        print("="*80)
        
    except requests.exceptions.ConnectionError:
        print("\nERROR: Cannot connect to Flask server!")
        print("   Make sure the server is running: python run.py")
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
