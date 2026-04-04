#!/usr/bin/env python3
"""
Test enhanced Python Code Quality MCP Server
"""

import asyncio
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Create test directory for database
os.makedirs("py_mcp/test_data", exist_ok=True)

from server import PythonCodeQualityServer


async def test_enhanced_features():
    """Test các tính năng enhanced mới"""
    
    # Initialize server
    server = PythonCodeQualityServer()
    
    print("=== Testing Enhanced Python Code Quality MCP Server ===")
    print(f"Server: {server.name} v{server.version}")
    print(f"Memory database: {server.memory_manager.db_path}")
    print()
    
    # Test 1: Learn from high-quality code
    print("Test 1: Learning from high-quality code")
    high_quality_code = '''
def calculate_fibonacci(n: int) -> int:
    """
    Calculate Fibonacci number with memoization.
    
    Args:
        n: Position in Fibonacci sequence
        
    Returns:
        Fibonacci number at position n
        
    Raises:
        ValueError: If n is negative
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    
    if n <= 1:
        return n
    
    # Use memoization for efficiency
    memo = {0: 0, 1: 1}
    
    for i in range(2, n + 1):
        memo[i] = memo[i-1] + memo[i-2]
    
    return memo[n]
'''
    
    learn_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "learn_from_code",
            "arguments": {
                "code": high_quality_code,
                "quality_score": 95.0
            }
        }
    }
    
    response = await server.handle_request(learn_request)
    if "result" in response:
        result_text = response["result"]["content"][0]["text"]
        result_data = json.loads(result_text)
        print(f"Learning result: {result_data['status']}")
        print(f"Patterns learned: {len(result_data['patterns_learned'])}")
        for pattern in result_data['patterns_learned']:
            print(f"  - {pattern['type']}: {pattern['quality_indicator']}")
    
    print("\n" + "="*60)
    
    # Test 2: Validate code with context
    print("\nTest 2: Enhanced validation with context memory")
    test_code = '''
def process_data(filename):
    file = open(filename, 'r')
    data = eval(file.read())
    return data * 2
'''
    
    validate_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "validate_code",
            "arguments": {"code": test_code}
        }
    }
    
    response = await server.handle_request(validate_request)
    if "result" in response:
        result_text = response["result"]["content"][0]["text"]
        result_data = json.loads(result_text)
        
        print(f"Status: {result_data['status']}")
        print(f"Quality improvement: {result_data['quality_analysis']['improvement']:.1f}")
        print(f"Context insights:")
        print(f"  - Similar contexts used: {result_data['context_insights']['similar_contexts_used']}")
        print(f"  - Memory size: {result_data['context_insights']['memory_size']}")
        print(f"  - Recommendations applied: {result_data['context_insights']['recommendations_applied']}")
        
        if 'detected_errors' in result_data:
            print(f"Errors fixed:")
            for error in result_data['detected_errors']:
                print(f"  - {error['type']}: {error['description']}")
    
    print("\n" + "="*60)
    
    # Test 3: Get context insights
    print("\nTest 3: Memory and context insights")
    insights_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_context_insights",
            "arguments": {}
        }
    }
    
    response = await server.handle_request(insights_request)
    if "result" in response:
        result_text = response["result"]["content"][0]["text"]
        result_data = json.loads(result_text)
        
        insights = result_data["context_insights"]
        print(f"Memory status: {result_data['memory_status']}")
        print(f"Active memory size: {insights['active_memory_size']}")
        print(f"Total code history: {insights['total_code_history']}")
        print(f"Average quality score: {insights['average_quality_score']}")
        print(f"Quality patterns learned: {insights['quality_patterns_learned']}")
        
        if insights['pattern_statistics']:
            print("Pattern statistics:")
            for stat in insights['pattern_statistics']:
                print(f"  - {stat['type']}: {stat['count']} times, avg quality {stat['avg_quality']}")
    
    print("\n" + "="*60)
    print("Enhanced testing completed!")
    print("\n🎉 New Features Summary:")
    print("✅ Memory management - Nhớ ngữ cảnh từ 50 code snippets gần nhất")
    print("✅ Quality learning - Học patterns từ code chất lượng cao")
    print("✅ Context awareness - Sử dụng historical context để suggest")
    print("✅ Pattern recognition - Phát hiện và học advanced patterns")
    print("✅ Quality scoring - Tính điểm chất lượng code (0-100)")
    print("✅ Enhanced validation - Sử dụng memory để improve suggestions")
    print("✅ Learning tool - Cho phép Copilot học từ examples")
    print("✅ Insights tool - Thống kê memory và learning progress")


if __name__ == "__main__":
    asyncio.run(test_enhanced_features())
