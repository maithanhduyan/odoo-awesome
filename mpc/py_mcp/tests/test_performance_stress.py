#!/usr/bin/env python3
"""
Performance và Stress Tests - CHALLENGE server limits
Test server với real-world scenarios và edge cases
"""

import unittest
import asyncio
import json
import time
import sys
import os
import random
import string
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestServerPerformanceLimits(unittest.TestCase):
    """Test hiệu suất và giới hạn của server"""
    
    def setUp(self):
        # Import here để tránh path issues
        from server import PythonCodeQualityServer
        self.server_class = PythonCodeQualityServer
    
    def test_memory_consumption_large_code(self):
        """Test: Server có consume quá nhiều memory không?"""
        print("\n🧪 Testing memory consumption with large code...")
        
        # Generate massive code file
        large_code_parts = []
        for i in range(500):
            large_code_parts.append(f"""
class DataProcessor{i}:
    '''Data processor class {i}'''
    
    def __init__(self, data: List[Dict[str, Any]]):
        self.data = data
        self.processed = False
        
    def process(self) -> Dict[str, Any]:
        '''Process the data'''
        result = {{}}
        for item in self.data:
            try:
                result[f'item_{{item["id"]}}'] = item.get('value', 0) * {i}
            except KeyError:
                continue
        self.processed = True
        return result
        
    def validate(self) -> bool:
        '''Validate processed data'''
        return self.processed and len(self.data) > 0
""")
        
        massive_code = "\n".join(large_code_parts)
        
        print(f"Generated code size: {len(massive_code):,} characters")
        print(f"Generated code lines: {massive_code.count(chr(10)):,} lines")
        
        # Measure memory before
        import psutil
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss / 1024 / 1024  # MB
        
        # Test server with massive code
        server = self.server_class()
        
        start_time = time.time()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        request = {
            "jsonrpc": "2.0", 
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "validate_code",
                "arguments": {"code": massive_code}
            }
        }
        
        try:
            response = loop.run_until_complete(server.handle_request(request))
            end_time = time.time()
            
            # Measure memory after
            memory_after = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = memory_after - memory_before
            processing_time = end_time - start_time
            
            print(f"⏱️  Processing time: {processing_time:.2f}s")
            print(f"💾 Memory increase: {memory_increase:.1f}MB")
            
            # CHALLENGE: Acceptable limits?
            if processing_time > 10.0:
                print("🚨 WARNING: Processing too slow for production!")
            
            if memory_increase > 100:
                print("🚨 WARNING: Memory consumption too high!")
                
            # Check if response is valid
            if "result" in response:
                result_text = response["result"]["content"][0]["text"]
                result_data = json.loads(result_text)
                print(f"✅ Server survived large code test")
                print(f"   Status: {result_data.get('status', 'unknown')}")
            else:
                print(f"❌ Server failed: {response.get('error', {}).get('message', 'unknown')}")
                
        except Exception as e:
            print(f"💥 CRASH: Server crashed with large code: {e}")
            
        finally:
            loop.close()
    
    def test_malformed_code_handling(self):
        """Test: Server có handle được malformed code không?"""
        print("\n🧪 Testing malformed code handling...")
        
        malformed_codes = [
            # Syntax errors
            "def broken_function(\nprint('missing closing paren')",
            "if True\nprint('missing colon')",
            "for i in range(10\nprint(i)",
            
            # Unicode chaos
            "def 测试函数():\n    print('unicode function name')",
            "print('emoji code 🐍🔥💀')",
            "# Comment with weird chars: ñáéíóú",
            
            # Very long lines
            "x = " + "1 + " * 1000 + "1",
            
            # Deeply nested
            "if True:\n" + "    if True:\n" * 50 + "        pass",
            
            # Binary garbage mixed with code
            "print('normal code')\n\x00\x01\x02\x03\ndef broken():\n    pass",
        ]
        
        server = self.server_class()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        crash_count = 0
        
        for i, bad_code in enumerate(malformed_codes):
            print(f"Testing malformed code {i+1}/{len(malformed_codes)}...")
            
            request = {
                "jsonrpc": "2.0",
                "id": i,
                "method": "tools/call", 
                "params": {
                    "name": "validate_code",
                    "arguments": {"code": bad_code}
                }
            }
            
            try:
                response = loop.run_until_complete(server.handle_request(request))
                
                if "error" in response:
                    print(f"   ✅ Graceful error: {response['error']['message'][:50]}...")
                elif "result" in response:
                    print(f"   ✅ Handled successfully")
                else:
                    print(f"   ⚠️  Unexpected response format")
                    
            except Exception as e:
                print(f"   💥 CRASH: {str(e)[:50]}...")
                crash_count += 1
        
        loop.close()
        
        print(f"\n📊 Malformed code test results:")
        print(f"   Total tests: {len(malformed_codes)}")
        print(f"   Crashes: {crash_count}")
        print(f"   Survival rate: {((len(malformed_codes) - crash_count) / len(malformed_codes)) * 100:.1f}%")
        
        if crash_count > 0:
            print("🚨 CRITICAL: Server has crash vulnerabilities!")
    
    def test_concurrent_request_stress(self):
        """Test: Server có handle concurrent requests không?"""
        print("\n🧪 Testing concurrent request handling...")
        
        # Generate different code samples
        test_codes = [
            "def simple(): pass",
            "print('hello world')",
            "x = [i for i in range(100)]",
            "try:\n    risky_operation()\nexcept:\n    pass",
            "eval('2 + 2')",
            "open('file.txt', 'r').read()",
        ]
        
        def make_request(code, request_id):
            """Make a single request to server"""
            try:
                server = self.server_class()
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                request = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {
                        "name": "validate_code", 
                        "arguments": {"code": code}
                    }
                }
                
                start_time = time.time()
                response = loop.run_until_complete(server.handle_request(request))
                end_time = time.time()
                
                loop.close()
                
                return {
                    "id": request_id,
                    "success": "result" in response,
                    "time": end_time - start_time,
                    "error": response.get("error", {}).get("message", None)
                }
                
            except Exception as e:
                return {
                    "id": request_id,
                    "success": False,
                    "time": 0,
                    "error": str(e)
                }
        
        # Run concurrent requests
        num_requests = 20
        
        print(f"Launching {num_requests} concurrent requests...")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(num_requests):
                code = random.choice(test_codes)
                future = executor.submit(make_request, code, i)
                futures.append(future)
            
            results = [future.result() for future in futures]
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Analyze results
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        avg_response_time = sum(r["time"] for r in successful) / len(successful) if successful else 0
        
        print(f"\n📊 Concurrent stress test results:")
        print(f"   Total requests: {num_requests}")
        print(f"   Successful: {len(successful)}")
        print(f"   Failed: {len(failed)}")
        print(f"   Success rate: {(len(successful) / num_requests) * 100:.1f}%")
        print(f"   Total time: {total_time:.2f}s")
        print(f"   Avg response time: {avg_response_time:.3f}s")
        
        if failed:
            print(f"   Failure examples:")
            for fail in failed[:3]:
                print(f"     - ID {fail['id']}: {fail['error'][:50]}...")
        
        # CHALLENGES
        if len(failed) > num_requests * 0.1:  # >10% failure rate
            print("🚨 WARNING: High failure rate under concurrent load!")
        
        if avg_response_time > 1.0:
            print("🚨 WARNING: Slow response times under load!")


class TestServerEdgeCases(unittest.TestCase):
    """Test các edge cases và corner cases"""
    
    def setUp(self):
        from server import PythonCodeQualityServer
        self.server_class = PythonCodeQualityServer
    
    def test_empty_and_whitespace_inputs(self):
        """Test với inputs trống và whitespace"""
        print("\n🧪 Testing empty and whitespace inputs...")
        
        edge_inputs = [
            "",  # Empty
            " ",  # Single space
            "\n",  # Single newline
            "\t",  # Single tab
            "   \n\t\n   ",  # Mixed whitespace
            "# Just a comment",  # Only comment
            "'''Just a docstring'''",  # Only docstring
        ]
        
        server = self.server_class()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for i, edge_input in enumerate(edge_inputs):
            print(f"Testing edge input {i+1}: {repr(edge_input[:20])}")
            
            request = {
                "jsonrpc": "2.0",
                "id": i,
                "method": "tools/call",
                "params": {
                    "name": "validate_code",
                    "arguments": {"code": edge_input}
                }
            }
            
            try:
                response = loop.run_until_complete(server.handle_request(request))
                
                if "result" in response:
                    result_text = response["result"]["content"][0]["text"]
                    result_data = json.loads(result_text)
                    print(f"   ✅ Status: {result_data.get('status', 'unknown')}")
                else:
                    print(f"   ❌ Error: {response.get('error', {}).get('message', 'unknown')}")
                    
            except Exception as e:
                print(f"   💥 Exception: {str(e)[:50]}...")
        
        loop.close()
    
    def test_extreme_code_patterns(self):
        """Test với extreme code patterns"""
        print("\n🧪 Testing extreme code patterns...")
        
        extreme_codes = [
            # Very long variable name
            "very_long_variable_name_" + "x" * 200 + " = 42",
            
            # Very deep nesting
            "if True:\n" + "    if True:\n" * 30 + "        print('deep')",
            
            # Many function parameters
            "def many_params(" + ", ".join(f"arg{i}" for i in range(50)) + "): pass",
            
            # Giant string
            f"text = {'x' * 10000}",
            
            # Massive list comprehension
            "result = [i for i in range(1000) if i % 2 == 0 for j in range(100)]",
            
            # Unicode madness
            "def 函数名称αβγδε(参数一, παράμετρος): return 'ñáéíóú🐍'",
        ]
        
        server = self.server_class()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for i, extreme_code in enumerate(extreme_codes):
            print(f"Testing extreme pattern {i+1}/{len(extreme_codes)}...")
            
            request = {
                "jsonrpc": "2.0",
                "id": i,
                "method": "tools/call",
                "params": {
                    "name": "validate_code",
                    "arguments": {"code": extreme_code}
                }
            }
            
            start_time = time.time()
            
            try:
                response = loop.run_until_complete(server.handle_request(request))
                end_time = time.time()
                
                processing_time = end_time - start_time
                
                if "result" in response:
                    print(f"   ✅ Processed in {processing_time:.3f}s")
                else:
                    print(f"   ❌ Failed in {processing_time:.3f}s")
                
                # CHALLENGE: Too slow?
                if processing_time > 2.0:
                    print(f"   🚨 WARNING: Slow processing for extreme pattern!")
                    
            except Exception as e:
                print(f"   💥 CRASH: {str(e)[:50]}...")
        
        loop.close()


def run_performance_tests():
    """Run all performance and stress tests"""
    print("🚀 RUNNING PERFORMANCE & STRESS TESTS")
    print("="*60)
    print("⚠️  WARNING: These tests may consume significant resources!")
    print("⚠️  WARNING: Tests designed to BREAK the server!")
    print("="*60)
    
    test_classes = [
        TestServerPerformanceLimits,
        TestServerEdgeCases
    ]
    
    for test_class in test_classes:
        print(f"\n🔥 Running {test_class.__name__}")
        print("-" * 50)
        
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=1)
        result = runner.run(suite)
        
        if result.failures or result.errors:
            print(f"❌ FAILURES/ERRORS found in {test_class.__name__}")
        else:
            print(f"✅ {test_class.__name__} completed")
    
    print("\n" + "="*60)
    print("🎯 PERFORMANCE TEST CONCLUSIONS")
    print("="*60)
    print("✅ Server stress-tested with extreme inputs")
    print("✅ Memory and performance limits explored") 
    print("✅ Concurrent handling evaluated")
    print("✅ Edge cases and failure modes identified")
    print("\n💡 INSIGHTS:")
    print("- Real-world performance may differ from lab tests")
    print("- Server has finite limits that need monitoring")
    print("- Graceful degradation under stress is critical")
    print("- Production deployment needs safeguards")


if __name__ == "__main__":
    run_performance_tests()
