"""
Test graph.py - MemOS LangGraph RAG Flow
"""
import asyncio
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Force reload environment
from dotenv import load_dotenv
load_dotenv(override=True)

# Clear any cached graph instance
import graph as graph_module
if hasattr(graph_module, '_graph_instance'):
    graph_module._graph_instance = None

from graph import chat


async def test_graph():
    """Test the complete graph flow"""
    print("=" * 60)
    print("MemOS Graph Test")
    print("=" * 60)

    # Test 1: WORK intent (should trigger deep search)
    print("\n[TEST 1] WORK Intent - Query about MemOS")
    print("-" * 60)
    try:
        result = await chat(
            "Tell me about the MemOS v2.0 project architecture",
            session_id="test-001"
        )
        print(f"Intent: {result['intent']}")
        print(f"Metadata: {result['metadata']}")
        print(f"Response preview:\n{result['response'][:300]}...")
        print("[OK] Test 1 passed")
    except Exception as e:
        print(f"[FAIL] Test 1: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: CHAT intent (should skip deep search)
    print("\n[TEST 2] CHAT Intent - Casual greeting")
    print("-" * 60)
    try:
        result = await chat(
            "Hello! How are you today?",
            session_id="test-002"
        )
        print(f"Intent: {result['intent']}")
        print(f"Metadata: {result['metadata']}")
        print(f"Response preview:\n{result['response'][:200]}...")
        print("[OK] Test 2 passed")
    except Exception as e:
        print(f"[FAIL] Test 2: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: With attachment simulation
    print("\n[TEST 3] WORK Intent with context")
    print("-" * 60)
    try:
        result = await chat(
            "What technology stack are we using for this project?",
            session_id="test-003"
        )
        print(f"Intent: {result['intent']}")
        print(f"Entities retrieved: {result['metadata'].get('total_entities', 0)}")
        print(f"Response preview:\n{result['response'][:300]}...")
        print("[OK] Test 3 passed")
    except Exception as e:
        print(f"[FAIL] Test 3: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_graph())
