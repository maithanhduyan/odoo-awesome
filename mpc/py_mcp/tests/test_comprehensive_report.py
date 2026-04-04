#!/usr/bin/env python3
"""
Comprehensive Test Report Generator for Python Code Quality MCP Server
Tạo báo cáo tổng hợp về hiệu suất và limitations của server
"""

import unittest
import os
import tempfile
import json
import time
from datetime import datetime
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from server import CodeMemoryManager, EnhancedCodeAnalyzer


class TestReportGenerator:
    """Generate comprehensive test reports"""
    
    def __init__(self):
        self.test_results = {
            "timestamp": datetime.now().isoformat(),
            "categories": {},
            "summary": {},
            "limitations_discovered": [],
            "recommendations": []
        }
    
    def run_comprehensive_tests(self):
        """Chạy tất cả test categories và tạo report"""
        print("🔬 PYTHON CODE QUALITY MCP SERVER - COMPREHENSIVE TEST REPORT")
        print("=" * 80)
        
        # 1. Basic functionality tests
        self._test_basic_functionality()
        
        # 2. Security detection tests
        self._test_security_detection()
        
        # 3. Performance analysis tests
        self._test_performance_analysis()
        
        # 4. Edge case handling
        self._test_edge_cases()
        
        # 5. Memory and learning tests
        self._test_memory_learning()
        
        # 6. Generate final report
        self._generate_final_report()
    
    def _test_basic_functionality(self):
        """Test basic code analysis functionality"""
        print("\n📋 Testing Basic Functionality...")
        
        test_db = tempfile.mktemp(suffix=".db")
        memory_manager = CodeMemoryManager(test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "issues_found": []
        }
        
        # Test 1: Safe code should get high score
        safe_code = """
def calculate_average(numbers: List[float]) -> float:
    '''Calculate the average of a list of numbers'''
    if not numbers:
        raise ValueError("Cannot calculate average of empty list")
    return sum(numbers) / len(numbers)
"""
        
        analysis = analyzer.analyze_with_context(safe_code)
        results["total_tests"] += 1
        
        if analysis["quality_score"] >= 70:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["issues_found"].append(f"Safe code got low score: {analysis['quality_score']}")
        
        # Test 2: Dangerous code should get low score
        dangerous_code = """
import os
def dangerous_function(user_input):
    os.system(user_input)
    eval(user_input)
    exec(user_input)
"""
        
        analysis = analyzer.analyze_with_context(dangerous_code)
        results["total_tests"] += 1
        
        if analysis["quality_score"] <= 30:
            results["passed"] += 1
        else:
            results["failed"] += 1
            results["issues_found"].append(f"Dangerous code got high score: {analysis['quality_score']}")
        
        self.test_results["categories"]["basic_functionality"] = results
        print(f"✅ Basic Tests: {results['passed']}/{results['total_tests']} passed")
        
        memory_manager.conn.close()
        try:
            os.remove(test_db)
        except:
            pass
    
    def _test_security_detection(self):
        """Test security vulnerability detection"""
        print("\n🔒 Testing Security Detection...")
        
        test_db = tempfile.mktemp(suffix=".db")
        memory_manager = CodeMemoryManager(test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        security_tests = [
            {
                "name": "Command Injection",
                "code": "import os; os.system(f'ls {user_input}')",
                "should_detect": True
            },
            {
                "name": "Eval Usage",
                "code": "result = eval(user_input)",
                "should_detect": True
            },
            {
                "name": "Pickle Deserialization",
                "code": "import pickle; data = pickle.loads(untrusted_input)",
                "should_detect": True
            },
            {
                "name": "SQL Injection",
                "code": f"cursor.execute(f'SELECT * FROM users WHERE id = {user_id}')",
                "should_detect": True
            },
            {
                "name": "Safe Alternative",
                "code": "import ast; result = ast.literal_eval(user_input)",
                "should_detect": False
            }
        ]
        
        results = {
            "total_tests": len(security_tests),
            "correctly_detected": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "detection_details": []
        }
        
        for test in security_tests:
            analysis = analyzer.analyze_with_context(test["code"])
            has_security_error = any(
                'security' in e.get('message', '').lower() or 
                'eval' in e.get('message', '').lower() or
                'dangerous' in e.get('message', '').lower()
                for e in analysis.get("errors", [])
            )
            
            low_score = analysis["quality_score"] < 50
            detected = has_security_error or low_score
            
            if test["should_detect"] and detected:
                results["correctly_detected"] += 1
                status = "✅ CORRECT"
            elif not test["should_detect"] and not detected:
                results["correctly_detected"] += 1
                status = "✅ CORRECT"
            elif test["should_detect"] and not detected:
                results["false_negatives"] += 1
                status = "❌ FALSE NEGATIVE"
            else:
                results["false_positives"] += 1
                status = "⚠️ FALSE POSITIVE"
            
            results["detection_details"].append({
                "test": test["name"],
                "status": status,
                "score": analysis["quality_score"],
                "errors": len(analysis.get("errors", []))
            })
        
        self.test_results["categories"]["security_detection"] = results
        print(f"🔒 Security Tests: {results['correctly_detected']}/{results['total_tests']} correct")
        
        if results["false_negatives"] > 0:
            self.test_results["limitations_discovered"].append(
                f"Security Detection: {results['false_negatives']} false negatives detected"
            )
        
        memory_manager.conn.close()
        try:
            os.remove(test_db)
        except:
            pass
    
    def _test_performance_analysis(self):
        """Test performance issue detection"""
        print("\n⚡ Testing Performance Analysis...")
        
        test_db = tempfile.mktemp(suffix=".db")
        memory_manager = CodeMemoryManager(test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        performance_tests = [
            {
                "name": "O(n²) nested loops",
                "code": """
def slow_search(data, target):
    for i in data:
        for j in data:
            if i == j == target:
                return True
    return False
""",
                "expected_score_range": (20, 60)  # Should detect inefficiency
            },
            {
                "name": "Efficient O(1) lookup",
                "code": """
def fast_search(data_set, target):
    return target in data_set
""",
                "expected_score_range": (60, 100)  # Should be rated highly
            },
            {
                "name": "Memory inefficient",
                "code": """
def memory_waste():
    huge_list = [i for i in range(1000000)]
    return len(huge_list)
""",
                "expected_score_range": (30, 70)  # May or may not detect
            }
        ]
        
        results = {
            "total_tests": len(performance_tests),
            "correct_assessments": 0,
            "performance_details": []
        }
        
        for test in performance_tests:
            analysis = analyzer.analyze_with_context(test["code"])
            score = analysis["quality_score"]
            
            min_expected, max_expected = test["expected_score_range"]
            correct = min_expected <= score <= max_expected
            
            if correct:
                results["correct_assessments"] += 1
                status = "✅ CORRECT RANGE"
            else:
                status = f"❌ OUTSIDE RANGE (got {score}, expected {min_expected}-{max_expected})"
            
            results["performance_details"].append({
                "test": test["name"],
                "status": status,
                "score": score,
                "expected_range": test["expected_score_range"]
            })
        
        self.test_results["categories"]["performance_analysis"] = results
        print(f"⚡ Performance Tests: {results['correct_assessments']}/{results['total_tests']} correct")
        
        memory_manager.conn.close()
        try:
            os.remove(test_db)
        except:
            pass
    
    def _test_edge_cases(self):
        """Test edge case handling"""
        print("\n🧪 Testing Edge Cases...")
        
        edge_cases = [
            ("Empty code", ""),
            ("Only whitespace", "   \n\t  \n  "),
            ("Only comments", "# This is just a comment\n# Another comment"),
            ("Unicode code", "def 函数(): return '中文'"),
            ("Very long line", "x = " + "1 + " * 1000 + "1"),
        ]
        
        test_db = tempfile.mktemp(suffix=".db")
        memory_manager = CodeMemoryManager(test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        results = {
            "total_tests": len(edge_cases),
            "handled_gracefully": 0,
            "crashed": 0,
            "edge_case_details": []
        }
        
        for name, code in edge_cases:
            try:
                analysis = analyzer.analyze_with_context(code)
                if isinstance(analysis, dict) and "quality_score" in analysis:
                    results["handled_gracefully"] += 1
                    status = "✅ HANDLED"
                else:
                    status = "⚠️ UNEXPECTED RESULT"
                    
            except Exception as e:
                results["crashed"] += 1
                status = f"❌ CRASHED: {str(e)[:50]}"
            
            results["edge_case_details"].append({
                "test": name,
                "status": status
            })
        
        self.test_results["categories"]["edge_cases"] = results
        print(f"🧪 Edge Cases: {results['handled_gracefully']}/{results['total_tests']} handled gracefully")
        
        memory_manager.conn.close()
        try:
            os.remove(test_db)
        except:
            pass
    
    def _test_memory_learning(self):
        """Test memory and learning capabilities"""
        print("\n🧠 Testing Memory & Learning...")
        
        test_db = tempfile.mktemp(suffix=".db")
        memory_manager = CodeMemoryManager(test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # Test learning from examples
        good_example = """
def efficient_function(data: List[int]) -> List[int]:
    '''Efficient list comprehension'''
    return [x * 2 for x in data if x > 0]
"""
        
        # Teach the server
        memory_manager.add_code_context(good_example, good_example, 95.0, ["list_comprehension"])
        
        # Test if it learned
        similar_code = """
def process_numbers(numbers):
    result = []
    for num in numbers:
        if num > 0:
            result.append(num * 2)
    return result
"""
        
        analysis = analyzer.analyze_with_context(similar_code)
        recommendations = analysis.get("recommendations", [])
        
        results = {
            "learning_test_passed": len(recommendations) > 0,
            "recommendations_count": len(recommendations),
            "memory_insights": memory_manager.get_context_insights()
        }
        
        self.test_results["categories"]["memory_learning"] = results
        print(f"🧠 Memory Tests: {'✅ PASSED' if results['learning_test_passed'] else '❌ FAILED'}")
        
        memory_manager.conn.close()
        try:
            os.remove(test_db)
        except:
            pass
    
    def _generate_final_report(self):
        """Generate and save final report"""
        print("\n📊 Generating Final Report...")
        
        # Calculate overall statistics
        total_tests = sum(
            cat.get("total_tests", 0) 
            for cat in self.test_results["categories"].values()
            if isinstance(cat.get("total_tests"), int)
        )
        
        total_passed = sum([
            self.test_results["categories"]["basic_functionality"]["passed"],
            self.test_results["categories"]["security_detection"]["correctly_detected"],
            self.test_results["categories"]["performance_analysis"]["correct_assessments"],
            self.test_results["categories"]["edge_cases"]["handled_gracefully"]
        ])
        
        overall_score = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        self.test_results["summary"] = {
            "overall_score": f"{overall_score:.1f}%",
            "total_tests": total_tests,
            "total_passed": total_passed,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add recommendations based on findings
        if self.test_results["categories"]["security_detection"]["false_negatives"] > 0:
            self.test_results["recommendations"].append(
                "Improve security vulnerability detection patterns"
            )
        
        if self.test_results["categories"]["performance_analysis"]["correct_assessments"] < 2:
            self.test_results["recommendations"].append(
                "Enhance performance analysis algorithms"
            )
        
        # Save report
        report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_results, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print("\n" + "=" * 80)
        print("📊 FINAL TEST REPORT SUMMARY")
        print("=" * 80)
        print(f"Overall Score: {overall_score:.1f}% ({total_passed}/{total_tests} tests passed)")
        print(f"Report saved to: {report_file}")
        
        print("\n🔍 Key Findings:")
        for limitation in self.test_results["limitations_discovered"]:
            print(f"  ⚠️  {limitation}")
        
        print("\n💡 Recommendations:")
        for rec in self.test_results["recommendations"]:
            print(f"  🔧 {rec}")
        
        print("\n📈 Category Breakdown:")
        for category, results in self.test_results["categories"].items():
            if isinstance(results, dict):
                if "passed" in results and "total_tests" in results:
                    score = results["passed"] / results["total_tests"] * 100
                    print(f"  {category}: {score:.1f}%")
                elif "correctly_detected" in results:
                    score = results["correctly_detected"] / results["total_tests"] * 100
                    print(f"  {category}: {score:.1f}%")


if __name__ == "__main__":
    generator = TestReportGenerator()
    generator.run_comprehensive_tests()
