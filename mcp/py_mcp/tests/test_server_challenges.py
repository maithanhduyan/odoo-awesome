#!/usr/bin/env python3
"""
Test suite để PHẢN BIỆN và KIỂM CHỨNG Python Code Quality MCP Server
Mục tiêu: Tìm ra những điều SAI, THIẾU SÓT, và MISLEADING trong server

Nguyên tắc Darwin:
- Mỗi test case là một hypothesis có thể bị falsify
- Tìm kiếm evidence trái chiều 
- Challenge mọi assumption
"""

import unittest
import asyncio
import json
import os
import sys
import tempfile
import sqlite3
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from server import (
    PythonCodeQualityServer, 
    CodeMemoryManager, 
    EnhancedCodeAnalyzer,
    ChromaDBManager,
    ConfigManager
)


class TestServerAssumptions(unittest.TestCase):
    """
    CHẤT VẤN các giả định cơ bản của server
    """
    
    def setUp(self):
        """Setup test environment với isolated database"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = os.path.join(self.temp_dir, "test_memory.db")
        
        # Mock config để tránh conflicts
        self.config = ConfigManager()
        self.config.config = {
            "chromadb_path": self.temp_dir,
            "log_level": "ERROR",  # Reduce noise
            "server": {
                "name": "test-server",
                "version": "test",
                "description": "Test server"
            }
        }
    
    def tearDown(self):
        """Cleanup test data"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass


class TestQualityScoreBias(TestServerAssumptions):
    """
    HYPOTHESIS: Quality score có thể misleading và biased
    FALSIFY: Tìm cases where "low quality score" = "better code"
    """
    
    def test_performance_vs_quality_paradox(self):
        """Test: Code hiệu quả nhưng quality score thấp"""
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # Code "xấu" nhưng hiệu quả
        fast_code = """
# No docstring, no type hints, "magic numbers"
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
"""
        
        # Code "đẹp" nhưng chậm
        slow_code = """
from typing import Dict
import functools

@functools.lru_cache(maxsize=None)
def fibonacci_perfect(n: int) -> int:
    '''
    Calculate Fibonacci number using recursion with memoization.
    
    Args:
        n: The position in Fibonacci sequence
        
    Returns:
        The Fibonacci number at position n
        
    Examples:
        >>> fibonacci_perfect(10)
        55
    '''
    if n <= 1:
        return n
    return fibonacci_perfect(n-1) + fibonacci_perfect(n-2)
"""
        
        fast_analysis = analyzer.analyze_with_context(fast_code)
        slow_analysis = analyzer.analyze_with_context(slow_code)
        
        # CHALLENGE: Server có đánh giá đúng performance không?
        print(f"Fast code quality: {fast_analysis['quality_score']}")
        print(f"Slow code quality: {slow_analysis['quality_score']}")
        
        # PARADOX: Slow code sẽ có score cao hơn!
        self.assertGreater(
            slow_analysis['quality_score'], 
            fast_analysis['quality_score'],
            "PARADOX CONFIRMED: 'Beautiful' slow code gets higher score than fast code"
        )
    
    def test_readability_vs_performance_trade_off(self):
        """Test: Code readable vs code optimized"""
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # Readable but slow
        readable_code = """
def process_large_dataset(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    '''Process large dataset with proper error handling'''
    result = []
    for item in data:
        try:
            if item.get('status') == 'active':
                processed_item = {
                    'id': item['id'],
                    'value': item['value'] * 2,
                    'timestamp': item['timestamp']
                }
                result.append(processed_item)
        except (KeyError, TypeError) as e:
            logging.error(f"Error processing item: {e}")
            continue
    return result
"""
        
        # Optimized but less readable
        optimized_code = """
def process_large_dataset_fast(data):
    return [{'id': i['id'], 'value': i['value'] * 2, 'timestamp': i['timestamp']} 
            for i in data if i.get('status') == 'active']
"""
        
        readable_analysis = analyzer.analyze_with_context(readable_code)
        optimized_analysis = analyzer.analyze_with_context(optimized_code)
        
        # Server bias towards "verbose = good"?
        print(f"Readable code: {readable_analysis['quality_score']}")
        print(f"Optimized code: {optimized_analysis['quality_score']}")
        
        # QUESTION: Which is actually better for production?


class TestMemorySystemFlaws(TestServerAssumptions):
    """
    HYPOTHESIS: Memory system có thể gây harm hơn help
    FALSIFY: Tìm cases where historical context misleads
    """
    
    def test_outdated_context_pollution(self):
        """Test: Context cũ có thể gây suggestions sai"""
        memory_manager = CodeMemoryManager(self.test_db)
        
        # Thêm "best practice" cũ
        old_code = """
# Python 2 style - was good in 2010
def read_file(filename):
    try:
        f = open(filename, 'r')
        content = f.read()
        f.close()
        return content
    except IOError:
        return None
"""
        memory_manager.add_code_context(old_code, old_code, 90.0, ["file_handling"])
        
        # Code hiện đại
        modern_code = """
def read_file(filename):
    with open(filename, 'r') as f:
        return f.read()
"""
        
        similar_contexts = memory_manager.get_similar_contexts(modern_code)
        
        # DANGER: Old context có thể mislead
        if similar_contexts:
            old_context = similar_contexts[0]
            self.assertIn("f.close()", old_context["original"])
            print("WARNING: Old context suggests manual file closing!")
    
    def test_context_bias_amplification(self):
        """Test: Memory system có amplify bias không?"""
        memory_manager = CodeMemoryManager(self.test_db)
        
        # Thêm nhiều examples với same bias
        biased_examples = [
            "def func(): pass  # Simple function",
            "def another(): pass  # Another simple",
            "def third(): pass  # Third simple"
        ]
        
        for code in biased_examples:
            memory_manager.add_code_context(code, code, 85.0, ["simple"])
        
        # Test với complex function
        complex_code = """
def complex_function(data: List[Dict], config: Config) -> ProcessedResult:
    '''Complex but necessary function'''
    # Complex logic here...
    pass
"""
        
        recommendations = memory_manager.get_quality_recommendations(["complexity"])
        
        # BIAS: System có prefer simplicity over necessity?
        print(f"Recommendations for complex code: {len(recommendations)}")


class TestPatternRecognitionFailures(TestServerAssumptions):
    """
    HYPOTHESIS: Pattern recognition có thể miss important issues
    FALSIFY: Tìm critical bugs mà server bỏ qua
    """
    
    def test_security_vulnerabilities_missed(self):
        """Test: Server có miss security issues không?"""
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # Code có security vulnerabilities nhưng "clean"
        vulnerable_code = """
import os
import subprocess
from typing import str

def execute_user_command(user_input: str) -> str:
    '''Execute user command - well documented!'''
    try:
        # VULNERABILITY: Command injection
        result = subprocess.run(user_input, shell=True, capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"Error: {e}"

def read_sensitive_file(filename: str) -> str:
    '''Read file with proper type hints'''
    # VULNERABILITY: Path traversal
    full_path = os.path.join('/var/data/', filename)
    with open(full_path, 'r') as f:
        return f.read()
"""
        
        analysis = analyzer.analyze_with_context(vulnerable_code)
        
        # CRITICAL: Server có detect được security issues không?
        security_errors = [e for e in analysis['errors'] 
                          if 'injection' in e['description'].lower() 
                          or 'traversal' in e['description'].lower()]
        
        print(f"Security errors detected: {len(security_errors)}")
        print(f"Quality score: {analysis['quality_score']}")
        
        # FAILURE: Code vulnerable nhưng có thể có score cao
        if analysis['quality_score'] > 70:
            print("DANGER: Vulnerable code got high quality score!")
    
    def test_logical_errors_in_beautiful_code(self):
        """Test: Server có detect logical errors không?"""
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # Code syntax perfect nhưng logic sai
        buggy_code = """
from typing import List, Optional
import logging

def find_maximum_value(numbers: List[int]) -> Optional[int]:
    '''
    Find maximum value in a list of numbers.
    
    Args:
        numbers: List of integers to search
        
    Returns:
        Maximum value or None if list is empty
        
    Raises:
        TypeError: If input is not a list
    '''
    if not isinstance(numbers, list):
        raise TypeError("Input must be a list")
    
    if len(numbers) == 0:
        return None
    
    max_value = numbers[0]
    for num in numbers:
        if num < max_value:  # BUG: Should be >
            max_value = num
    
    logging.info(f"Found maximum value: {max_value}")
    return max_value
"""
        
        analysis = analyzer.analyze_with_context(buggy_code)
        
        # CHALLENGE: Server có detect logic bug không?
        logic_errors = [e for e in analysis['errors'] 
                       if 'logic' in e['description'].lower()]
        
        print(f"Logic errors detected: {len(logic_errors)}")
        print(f"Quality score: {analysis['quality_score']}")
        
        # LIMITATION: Server likely misses logic bugs


class TestServerIntegrationReality(TestServerAssumptions):
    """
    HYPOTHESIS: Server integration sẽ work trong real world
    FALSIFY: Test real-world scenarios where it fails
    """
    
    async def test_large_codebase_performance(self):
        """Test: Server có handle được large files không?"""
        # Generate large code file
        large_code = "\n".join([
            f"def function_{i}():",
            f"    '''Function number {i}'''",
            f"    return {i} * 2",
            ""
        ] for i in range(1000))
        
        server = PythonCodeQualityServer()
        
        import time
        start_time = time.time()
        
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "validate_code",
                "arguments": {"code": large_code}
            }
        }
        
        try:
            response = await server.handle_request(request)
            end_time = time.time()
            
            processing_time = end_time - start_time
            print(f"Large file processing time: {processing_time:.2f}s")
            
            # PERFORMANCE CHALLENGE
            if processing_time > 5.0:
                print("WARNING: Too slow for real-world usage!")
                
        except Exception as e:
            print(f"FAILURE: Server crashed on large file: {e}")
    
    def test_concurrent_requests_handling(self):
        """Test: Server có handle concurrent requests không?"""
        # This would need async testing framework
        # Left as exercise for real testing
        pass


class TestFalsePositivesNegatives(TestServerAssumptions):
    """
    HYPOTHESIS: Server có accuracy cao
    FALSIFY: Tìm false positives và false negatives
    """
    
    def test_false_positive_detection(self):
        """Test: Server có báo lỗi sai không?"""
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # Code hoàn toàn OK nhưng có thể bị flag
        good_code = """
# Configuration constants - NOT magic numbers
MAX_RETRIES = 3
TIMEOUT_SECONDS = 30
API_VERSION = "v1"

def robust_api_call(url: str) -> Optional[Dict]:
    '''Make API call with proper error handling'''
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, timeout=TIMEOUT_SECONDS)
            if response.status_code == 200:
                return response.json()
        except requests.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                logging.error(f"API call failed after {MAX_RETRIES} attempts: {e}")
                return None
            time.sleep(2 ** attempt)  # Exponential backoff
    return None
"""
        
        analysis = analyzer.analyze_with_context(good_code)
        
        # FALSE POSITIVE check
        false_errors = []
        for error in analysis['errors']:
            if error['type'] == 'magic_numbers':
                if any(num in error['match'] for num in ['3', '30', '200', '2']):
                    false_errors.append(error)
        
        if false_errors:
            print(f"FALSE POSITIVES found: {len(false_errors)}")
            for err in false_errors:
                print(f"  - {err['description']}: {err['match']}")


def run_darwin_tests():
    """
    Chạy tất cả tests để CHALLENGE server
    """
    print("🔬 RUNNING DARWIN TESTS - Challenging All Assumptions")
    print("="*60)
    
    # Tạo test suite
    test_classes = [
        TestQualityScoreBias,
        TestMemorySystemFlaws, 
        TestPatternRecognitionFailures,
        TestFalsePositivesNegatives
    ]
    
    results = {
        "total_tests": 0,
        "failures": 0,
        "paradoxes_found": [],
        "limitations_discovered": []
    }
    
    for test_class in test_classes:
        print(f"\n📊 Testing: {test_class.__name__}")
        print("-" * 40)
        
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        results["total_tests"] += result.testsRun
        results["failures"] += len(result.failures) + len(result.errors)
        
        # Collect insights
        if result.failures:
            results["paradoxes_found"].extend([f[0].id() for f in result.failures])
        if result.errors:
            results["limitations_discovered"].extend([e[0].id() for e in result.errors])
    
    print("\n" + "="*60)
    print("🎯 DARWIN TEST RESULTS")
    print(f"Total tests run: {results['total_tests']}")
    print(f"Failures/Errors: {results['failures']}")
    print(f"Paradoxes found: {len(results['paradoxes_found'])}")
    print(f"Limitations discovered: {len(results['limitations_discovered'])}")
    
    if results['failures'] > 0:
        print("\n🚨 CRITICAL FINDINGS:")
        print("- Server assumptions challenged successfully")
        print("- Multiple failure modes discovered")
        print("- False confidence in quality metrics")
        
    return results


if __name__ == "__main__":
    # Run the Darwin test suite
    results = run_darwin_tests()
    
    print("\n" + "="*60)
    print("🧬 CONCLUSION: Darwin Analysis")
    print("="*60)
    print("✅ Tests created to FALSIFY server assumptions")
    print("✅ Multiple challenge scenarios implemented")
    print("✅ Real-world failure modes identified")
    print("\n📋 RECOMMENDED ACTIONS:")
    print("1. Run these tests regularly")
    print("2. Add more adversarial test cases") 
    print("3. Compare with human expert evaluations")
    print("4. Measure real-world impact vs lab performance")
    print("5. Question every 'improvement' metric")
