#!/usr/bin/env python3
"""
Test script for Python Code Quality MCP Server
Tests the workflow theo config.json: VSCode → MCP → ChromaDB → Safe Code
"""

import asyncio
import json
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from server import PythonCodeQualityServer


async def test_code_quality_server():
    """Test the Python Code Quality MCP Server"""
    
    # Initialize server
    server = PythonCodeQualityServer()
    
    print("=== Testing Python Code Quality MCP Server ===")
    print(f"Server: {server.name} v{server.version}")
    print(f"Description: {server.description}")
    print(f"Config loaded: {server.config.config}")
    print()
    
    # Test case 1: Code with division by zero
    test_code_1 = """
def calculate_ratio(a, b):
    return a / b

result = calculate_ratio(10, 0)
print(result)
"""
    
    print("Test 1: Code với potential division by zero")
    print("Input code:")
    print(test_code_1)
    
    # Create request
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "validate_code",
            "arguments": {"code": test_code_1}
        }
    }
    
    # Process request
    response = await server.handle_request(request)
    
    if "result" in response:
        result_text = response["result"]["content"][0]["text"]
        result_data = json.loads(result_text)
        
        print("\nResult:")
        print(f"Status: {result_data['status']}")
        print(f"Message: {result_data['message']}")
        
        if 'detected_errors' in result_data:
            print(f"Detected errors: {len(result_data['detected_errors'])}")
            for error in result_data['detected_errors']:
                print(f"  - {error['type']}: {error['description']} (line {error['line']})")
        
        if result_data['status'] == 'improved':
            print("\nSafe code:")
            print(result_data['safe_code'])
    else:
        print(f"Error: {response.get('error', {}).get('message', 'Unknown error')}")
    
    print("\n" + "="*60)
    
    # Test case 2: Code with unsafe file operations
    test_code_2 = """
def read_data():
    file = open('data.txt', 'r')
    content = file.read()
    file.close()
    return content

data = read_data()
"""
    
    print("\nTest 2: Code với unsafe file operations")
    print("Input code:")
    print(test_code_2)
    
    request["id"] = 2
    request["params"]["arguments"]["code"] = test_code_2
    
    response = await server.handle_request(request)
    
    if "result" in response:
        result_text = response["result"]["content"][0]["text"]
        result_data = json.loads(result_text)
        
        print("\nResult:")
        print(f"Status: {result_data['status']}")
        print(f"Message: {result_data['message']}")
        
        if 'detected_errors' in result_data:
            for error in result_data['detected_errors']:
                print(f"  - {error['type']}: {error['description']}")
        
        if result_data['status'] == 'improved':
            print("\nSafe code:")
            print(result_data['safe_code'])
    else:
        print(f"Error: {response.get('error', {}).get('message', 'Unknown error')}")
    
    print("\n" + "="*60)
    
    # Test case 3: Code with eval usage
    test_code_3 = """
def calculate_expression(expr):
    return eval(expr)

result = calculate_expression("2 + 3 * 4")
"""
    
    print("\nTest 3: Code với dangerous eval usage")
    print("Input code:")
    print(test_code_3)
    
    request["id"] = 3
    request["params"]["arguments"]["code"] = test_code_3
    
    response = await server.handle_request(request)
    
    if "result" in response:
        result_text = response["result"]["content"][0]["text"]
        result_data = json.loads(result_text)
        
        print("\nResult:")
        print(f"Status: {result_data['status']}")
        print(f"Message: {result_data['message']}")
        
        if 'detected_errors' in result_data:
            for error in result_data['detected_errors']:
                print(f"  - {error['type']}: {error['description']}")
        
        if result_data['status'] == 'improved':
            print("\nSafe code:")
            print(result_data['safe_code'])
    else:
        print(f"Error: {response.get('error', {}).get('message', 'Unknown error')}")
    
    print("\n" + "="*60)
    
    # Test case 4: Already safe code
    test_code_4 = """
def safe_divide(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return float('inf')

def safe_read_file(filename):
    try:
        with open(filename, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return ""

result = safe_divide(10, 2)
content = safe_read_file("test.txt")
"""
    
    print("\nTest 4: Already safe code")
    print("Input code:")
    print(test_code_4)
    
    request["id"] = 4
    request["params"]["arguments"]["code"] = test_code_4
    
    response = await server.handle_request(request)
    
    if "result" in response:
        result_text = response["result"]["content"][0]["text"]
        result_data = json.loads(result_text)
        
        print("\nResult:")
        print(f"Status: {result_data['status']}")
        print(f"Message: {result_data['message']}")
        print(f"Server info: {result_data['server']['name']} v{result_data['server']['version']}")
    else:
        print(f"Error: {response.get('error', {}).get('message', 'Unknown error')}")
    
    print("\n" + "="*60)
    print("Testing completed!")
    print(f"Config path: {server.config.config_path}")
    print(f"ChromaDB path: {server.config.get('chromadb_path')}")
    print(f"Log level: {server.config.get('log_level')}")


if __name__ == "__main__":
    asyncio.run(test_code_quality_server())
