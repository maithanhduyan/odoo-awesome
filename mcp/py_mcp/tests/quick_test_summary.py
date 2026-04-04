#!/usr/bin/env python3
"""
Quick Test Summary for Python Code Quality MCP Server
Kiểm tra nhanh các chức năng chính và tạo báo cáo
"""

import sys
import os
import tempfile
import json
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from server import CodeMemoryManager, EnhancedCodeAnalyzer


def test_server_capabilities():
    """Test nhanh các khả năng chính của server"""
    print("🔬 QUICK SERVER CAPABILITY TEST")
    print("=" * 50)
    
    # Create temporary database
    test_db = tempfile.mktemp(suffix=".db")
    memory_manager = CodeMemoryManager(test_db)
    analyzer = EnhancedCodeAnalyzer(memory_manager)
    
    results = {
        "basic_analysis": None,
        "security_detection": None, 
        "quality_scoring": None,
        "memory_learning": None,
        "edge_case_handling": None
    }
    
    # Test 1: Basic Analysis
    print("\n1️⃣ Testing Basic Code Analysis...")
    try:
        simple_code = """
def hello_world():
    print("Hello, World!")
    return "success"
"""
        analysis = analyzer.analyze_with_context(simple_code)
        results["basic_analysis"] = {
            "status": "✅ PASS",
            "quality_score": analysis["quality_score"],
            "errors_count": len(analysis.get("errors", []))
        }
        print(f"   Quality Score: {analysis['quality_score']}")
        print(f"   Errors: {len(analysis.get('errors', []))}")
    except Exception as e:
        results["basic_analysis"] = {"status": f"❌ FAIL: {e}"}
    
    # Test 2: Security Detection
    print("\n2️⃣ Testing Security Detection...")
    try:
        dangerous_code = """
import os
def bad_function(user_input):
    os.system(user_input)  # Command injection
    eval(user_input)       # Code injection
"""
        analysis = analyzer.analyze_with_context(dangerous_code)
        security_score = analysis["quality_score"]
        
        # Check if detected as dangerous (low score)
        if security_score < 50:
            status = "✅ DETECTED"
        else:
            status = f"⚠️ MISSED (score: {security_score})"
            
        results["security_detection"] = {
            "status": status,
            "quality_score": security_score,
            "errors_count": len(analysis.get("errors", []))
        }
        print(f"   Security Score: {security_score}")
        print(f"   Detection Status: {status}")
    except Exception as e:
        results["security_detection"] = {"status": f"❌ FAIL: {e}"}
    
    # Test 3: Quality Scoring Differentiation
    print("\n3️⃣ Testing Quality Score Differentiation...")
    try:
        bad_code = "def f(x): return x"  # Poor style
        good_code = """
def calculate_sum(numbers: List[int]) -> int:
    '''Calculate the sum of a list of numbers'''
    return sum(numbers)
"""
        
        bad_analysis = analyzer.analyze_with_context(bad_code)
        good_analysis = analyzer.analyze_with_context(good_code)
        
        bad_score = bad_analysis["quality_score"]
        good_score = good_analysis["quality_score"]
        
        if good_score > bad_score:
            status = "✅ DIFFERENTIATED"
        else:
            status = f"⚠️ NO DIFF (bad:{bad_score}, good:{good_score})"
            
        results["quality_scoring"] = {
            "status": status,
            "bad_score": bad_score,
            "good_score": good_score,
            "difference": good_score - bad_score
        }
        print(f"   Bad Code Score: {bad_score}")
        print(f"   Good Code Score: {good_score}")
        print(f"   Differentiation: {status}")
    except Exception as e:
        results["quality_scoring"] = {"status": f"❌ FAIL: {e}"}
    
    # Test 4: Memory Learning
    print("\n4️⃣ Testing Memory Learning...")
    try:
        # Teach a pattern
        learning_code = "def func(): return [x*2 for x in range(10)]"
        memory_manager.add_code_context(learning_code, learning_code, 90.0, ["list_comp"])
        
        # Test recall
        insights = memory_manager.get_context_insights()
        
        if insights["total_contexts"] > 0:
            status = "✅ LEARNING"
        else:
            status = "❌ NO MEMORY"
            
        results["memory_learning"] = {
            "status": status,
            "total_contexts": insights["total_contexts"],
            "avg_quality": insights["avg_quality"]
        }
        print(f"   Memory Status: {status}")
        print(f"   Stored Contexts: {insights['total_contexts']}")
    except Exception as e:
        results["memory_learning"] = {"status": f"❌ FAIL: {e}"}
    
    # Test 5: Edge Case Handling
    print("\n5️⃣ Testing Edge Case Handling...")
    edge_cases = [
        ("Empty", ""),
        ("Whitespace", "   \n  \t  "),
        ("Unicode", "def 测试(): pass"),
        ("Very Long", "x = " + " + ".join(str(i) for i in range(100)))
    ]
    
    handled_count = 0
    total_count = len(edge_cases)
    
    for name, code in edge_cases:
        try:
            analysis = analyzer.analyze_with_context(code)
            if isinstance(analysis, dict) and "quality_score" in analysis:
                handled_count += 1
                print(f"   {name}: ✅ HANDLED")
            else:
                print(f"   {name}: ⚠️ UNEXPECTED")
        except Exception as e:
            print(f"   {name}: ❌ FAILED ({str(e)[:30]})")
    
    results["edge_case_handling"] = {
        "status": f"✅ {handled_count}/{total_count} HANDLED",
        "handled": handled_count,
        "total": total_count,
        "success_rate": handled_count / total_count * 100
    }
    
    # Cleanup
    memory_manager.conn.close()
    try:
        os.remove(test_db)
    except:
        pass
    
    # Summary
    print("\n📊 QUICK TEST SUMMARY")
    print("=" * 50)
    
    passed_tests = 0
    total_tests = 5
    
    for test_name, result in results.items():
        status = result.get("status", "UNKNOWN")
        if "✅" in status:
            passed_tests += 1
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
    
    # Key findings
    print("\n🔍 KEY FINDINGS:")
    
    if results["security_detection"]["status"].startswith("⚠️"):
        print("  ⚠️  Security detection needs improvement")
    
    if results["quality_scoring"]["difference"] < 10:
        print("  ⚠️  Quality scoring differentiation is weak")
    
    if results["edge_case_handling"]["success_rate"] < 80:
        print("  ⚠️  Edge case handling needs work")
    
    print("\n💡 RECOMMENDATIONS:")
    print("  🔧 Add more security vulnerability patterns")
    print("  🔧 Improve quality score calculation algorithm")
    print("  🔧 Add performance analysis capabilities")
    print("  🔧 Enhance error detection for logical bugs")
    
    return results


if __name__ == "__main__":
    test_server_capabilities()
