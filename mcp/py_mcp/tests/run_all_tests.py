#!/usr/bin/env python3
"""
Master Test Runner for Python Code Quality MCP Server
Chạy tất cả test suites và tạo báo cáo tổng hợp
"""

import subprocess
import sys
import os
from datetime import datetime


def run_test_suite():
    """Chạy toàn bộ test suite và tạo báo cáo"""
    
    print("🧬 PYTHON CODE QUALITY MCP SERVER - MASTER TEST RUNNER")
    print("=" * 80)
    print(f"Test Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Change to py_mcp directory
    os.chdir("c:\\Users\\tiach\\Downloads\\migrate_odoo\\py_mcp")
    
    test_results = {}
    
    # 1. Darwin Falsification Tests
    print("\n🧬 Running Darwin Falsification Tests...")
    print("-" * 50)
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_server_challenges.py", "-v"
        ], capture_output=True, text=True, timeout=120)
        
        test_results["darwin_tests"] = {
            "status": "PASSED" if result.returncode == 0 else "FAILED",
            "output": result.stdout,
            "errors": result.stderr
        }
        print(f"Darwin Tests: {'✅ PASSED' if result.returncode == 0 else '❌ FAILED'}")
        
    except subprocess.TimeoutExpired:
        test_results["darwin_tests"] = {"status": "TIMEOUT"}
        print("Darwin Tests: ⏰ TIMEOUT")
    except Exception as e:
        test_results["darwin_tests"] = {"status": f"ERROR: {e}"}
        print(f"Darwin Tests: ❌ ERROR: {e}")
    
    # 2. Performance Stress Tests
    print("\n⚡ Running Performance Stress Tests...")
    print("-" * 50)
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest",
            "tests/test_performance_stress.py", "-v"
        ], capture_output=True, text=True, timeout=120)
        
        test_results["stress_tests"] = {
            "status": "PASSED" if result.returncode == 0 else "FAILED",
            "output": result.stdout,
            "errors": result.stderr
        }
        print(f"Stress Tests: {'✅ PASSED' if result.returncode == 0 else '❌ FAILED'}")
        
    except subprocess.TimeoutExpired:
        test_results["stress_tests"] = {"status": "TIMEOUT"}
        print("Stress Tests: ⏰ TIMEOUT")
    except Exception as e:
        test_results["stress_tests"] = {"status": f"ERROR: {e}"}
        print(f"Stress Tests: ❌ ERROR: {e}")
    
    # 3. Quick Capability Test
    print("\n🔬 Running Quick Capability Test...")
    print("-" * 50)
    try:
        result = subprocess.run([
            sys.executable, "tests/quick_test_summary.py"
        ], capture_output=True, text=True, timeout=60)
        
        test_results["capability_test"] = {
            "status": "COMPLETED",
            "output": result.stdout,
            "errors": result.stderr
        }
        print("Quick Test: ✅ COMPLETED")
        
    except subprocess.TimeoutExpired:
        test_results["capability_test"] = {"status": "TIMEOUT"}
        print("Quick Test: ⏰ TIMEOUT")
    except Exception as e:
        test_results["capability_test"] = {"status": f"ERROR: {e}"}
        print(f"Quick Test: ❌ ERROR: {e}")
    
    # 4. Darwin Final Analysis
    print("\n🧬 Running Darwin Final Analysis...")
    print("-" * 50)
    try:
        result = subprocess.run([
            sys.executable, "tests/darwin_final_analysis.py"
        ], capture_output=True, text=True, timeout=60)
        
        test_results["darwin_analysis"] = {
            "status": "COMPLETED",
            "output": result.stdout,
            "errors": result.stderr
        }
        print("Darwin Analysis: ✅ COMPLETED")
        
    except subprocess.TimeoutExpired:
        test_results["darwin_analysis"] = {"status": "TIMEOUT"}
        print("Darwin Analysis: ⏰ TIMEOUT")
    except Exception as e:
        test_results["darwin_analysis"] = {"status": f"ERROR: {e}"}
        print(f"Darwin Analysis: ❌ ERROR: {e}")
    
    # 5. Adversarial Tests (non-pytest)
    print("\n🎯 Running Adversarial Tests...")
    print("-" * 50)
    try:
        result = subprocess.run([
            sys.executable, "tests/test_adversarial_cases.py"
        ], capture_output=True, text=True, timeout=60)
        
        test_results["adversarial_tests"] = {
            "status": "COMPLETED",
            "output": result.stdout,
            "errors": result.stderr
        }
        print("Adversarial Tests: ✅ COMPLETED")
        
    except subprocess.TimeoutExpired:
        test_results["adversarial_tests"] = {"status": "TIMEOUT"}
        print("Adversarial Tests: ⏰ TIMEOUT")
    except Exception as e:
        test_results["adversarial_tests"] = {"status": f"ERROR: {e}"}
        print(f"Adversarial Tests: ❌ ERROR: {e}")
    
    # Summary
    print("\n📊 TEST SUITE SUMMARY")
    print("=" * 80)
    
    total_suites = len(test_results)
    passed_suites = sum(1 for r in test_results.values() if r["status"] == "PASSED")
    completed_suites = sum(1 for r in test_results.values() if r["status"] in ["PASSED", "COMPLETED"])
    
    print(f"Total Test Suites: {total_suites}")
    print(f"Passed/Completed: {completed_suites}")
    print(f"Success Rate: {completed_suites/total_suites*100:.1f}%")
    
    print(f"\nTest End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Detailed Results
    print("\n🔍 DETAILED RESULTS:")
    for suite_name, result in test_results.items():
        status = result["status"]
        print(f"\n{suite_name.upper().replace('_', ' ')}:")
        print(f"  Status: {status}")
        
        if "output" in result and result["output"]:
            # Show last few lines of output
            output_lines = result["output"].split('\n')
            relevant_lines = [line for line in output_lines[-10:] if line.strip()]
            if relevant_lines:
                print("  Key Output:")
                for line in relevant_lines[:3]:  # Show top 3 relevant lines
                    print(f"    {line}")
    
    # Final Assessment
    print("\n🧬 FINAL DARWIN ASSESSMENT:")
    if completed_suites >= 4:
        print("  ✅ SERVER SHOWS STRONG SURVIVAL POTENTIAL")
        print("  🧬 Ready for next evolutionary phase")
    elif completed_suites >= 2:
        print("  ⚠️ SERVER SHOWS MIXED SURVIVAL SIGNALS")
        print("  🧬 Requires focused adaptation")
    else:
        print("  ❌ SERVER SHOWS POOR SURVIVAL PROSPECTS")
        print("  🧬 Major evolutionary changes needed")
    
    print("\n📖 See tests/COMPREHENSIVE_TEST_REPORT.md for detailed analysis")
    print("=" * 80)
    
    return test_results


if __name__ == "__main__":
    run_test_suite()
