#!/usr/bin/env python3
"""
Final Test Summary và Darwin-style Analysis Report
Báo cáo cuối cùng với phân tích theo tinh thần Darwin về server
"""

import os
import sys
import tempfile
import json
from datetime import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from server import CodeMemoryManager, EnhancedCodeAnalyzer


def generate_darwin_analysis_report():
    """Tạo báo cáo phân tích theo tinh thần Darwin"""
    
    print("🧬 DARWIN-STYLE ANALYSIS: PYTHON CODE QUALITY MCP SERVER")
    print("=" * 80)
    print("Phân tích theo tinh thần khoa học: challenge every assumption")
    print("Survival of the fittest ideas - falsi cứ liệu có đúng không?")
    print("=" * 80)
    
    report = {
        "analysis_timestamp": datetime.now().isoformat(),
        "hypotheses_tested": [],
        "survival_results": {},
        "evolutionary_findings": {},
        "falsification_attempts": {},
        "fitness_assessment": {}
    }
    
    test_db = tempfile.mktemp(suffix=".db")
    memory_manager = CodeMemoryManager(test_db)
    analyzer = EnhancedCodeAnalyzer(memory_manager)
    
    print("\n🔬 HYPOTHESIS TESTING (Darwin's Method)")
    print("-" * 60)
    
    # Hypothesis 1: Server can distinguish good vs bad code
    print("\n1️⃣ HYPOTHESIS: Server can reliably distinguish code quality")
    
    test_cases = [
        ("Excellent Code", """
from typing import List, Optional
import logging

def calculate_statistics(data: List[float]) -> Optional[dict]:
    '''
    Calculate comprehensive statistics for a dataset.
    
    Args:
        data: List of numerical values
        
    Returns:
        Dictionary containing statistical measures or None if invalid input
        
    Raises:
        ValueError: If data is empty or contains non-numeric values
    '''
    if not data:
        raise ValueError("Dataset cannot be empty")
    
    try:
        cleaned_data = [float(x) for x in data]
    except (ValueError, TypeError) as e:
        raise ValueError(f"All data must be numeric: {e}")
    
    n = len(cleaned_data)
    mean_val = sum(cleaned_data) / n
    sorted_data = sorted(cleaned_data)
    
    if n % 2 == 0:
        median_val = (sorted_data[n//2 - 1] + sorted_data[n//2]) / 2
    else:
        median_val = sorted_data[n//2]
    
    variance = sum((x - mean_val) ** 2 for x in cleaned_data) / n
    std_dev = variance ** 0.5
    
    return {
        'count': n,
        'mean': mean_val,
        'median': median_val,
        'std_dev': std_dev,
        'min': min(cleaned_data),
        'max': max(cleaned_data)
    }
""", "should_be_high"),
        
        ("Terrible Code", """
import os
def func(x):
 y=eval(x)
 os.system("rm -rf /")
 return y
""", "should_be_low"),
        
        ("Subtle Bad Code", """
def process_user_data(users):
    # Looks innocent but has logical bugs
    total = 0
    for user in users:
        if user.age > 0:  # Bug: what about age = 0?
            total += user.age
        # Bug: no error handling for missing attributes
    return total / len(users)  # Bug: division by zero if empty list
""", "should_be_medium")
    ]
    
    quality_detection_results = []
    
    for name, code, expectation in test_cases:
        analysis = analyzer.analyze_with_context(code)
        score = analysis["quality_score"]
        
        if expectation == "should_be_high" and score >= 70:
            result = "✅ CORRECT"
        elif expectation == "should_be_low" and score <= 40:
            result = "✅ CORRECT"
        elif expectation == "should_be_medium" and 40 < score < 70:
            result = "✅ CORRECT"
        else:
            result = f"❌ WRONG (expected {expectation}, got {score})"
        
        quality_detection_results.append({
            "case": name,
            "score": score,
            "expectation": expectation,
            "result": result
        })
        
        print(f"   {name}: {score} → {result}")
    
    # Hypothesis 2: Memory system actually improves suggestions
    print("\n2️⃣ HYPOTHESIS: Memory system improves over time")
    
    # Before learning
    test_code = """
def double_list(items):
    result = []
    for item in items:
        result.append(item * 2)
    return result
"""
    
    before_analysis = analyzer.analyze_with_context(test_code)
    before_recommendations = len(before_analysis.get("recommendations", []))
    
    # Teach better pattern
    good_pattern = """
def double_list(items: List[int]) -> List[int]:
    '''Double each item in the list using list comprehension'''
    return [item * 2 for item in items]
"""
    
    memory_manager.add_code_context(
        test_code, good_pattern, 90.0, 
        [{"type": "list_comprehension", "code": "[item * 2 for item in items]"}]
    )
    
    # After learning
    after_analysis = analyzer.analyze_with_context(test_code)
    after_recommendations = len(after_analysis.get("recommendations", []))
    
    learning_improved = after_recommendations > before_recommendations
    
    print(f"   Before learning: {before_recommendations} recommendations")
    print(f"   After learning: {after_recommendations} recommendations")
    print(f"   Learning Effect: {'✅ IMPROVED' if learning_improved else '❌ NO CHANGE'}")
    
    # Hypothesis 3: Server detects actual security issues
    print("\n3️⃣ HYPOTHESIS: Server detects real security vulnerabilities")
    
    security_tests = [
        ("SQL Injection", "cursor.execute('SELECT * FROM users WHERE id = ' + user_id)"),
        ("Command Injection", "os.system('ls ' + user_input)"),
        ("Path Traversal", "open('../../../etc/passwd')"),
        ("Eval Usage", "eval(user_input)"),
        ("Pickle Vuln", "pickle.loads(untrusted_data)")
    ]
    
    security_detection_count = 0
    
    for vuln_name, vuln_code in security_tests:
        analysis = analyzer.analyze_with_context(vuln_code)
        detected = analysis["quality_score"] < 50 or any(
            'security' in e.get('message', '').lower() or
            'dangerous' in e.get('message', '').lower() or
            'eval' in e.get('message', '').lower()
            for e in analysis.get("errors", [])
        )
        
        if detected:
            security_detection_count += 1
            print(f"   {vuln_name}: ✅ DETECTED (score: {analysis['quality_score']})")
        else:
            print(f"   {vuln_name}: ❌ MISSED (score: {analysis['quality_score']})")
    
    # DARWIN CONCLUSION
    print("\n🧬 DARWIN'S SURVIVAL ASSESSMENT")
    print("=" * 60)
    
    # Calculate fitness scores
    quality_fitness = sum(1 for r in quality_detection_results if "✅" in r["result"]) / len(quality_detection_results)
    learning_fitness = 1.0 if learning_improved else 0.0
    security_fitness = security_detection_count / len(security_tests)
    
    overall_fitness = (quality_fitness + learning_fitness + security_fitness) / 3
    
    print(f"Quality Detection Fitness: {quality_fitness:.2f} ({quality_fitness*100:.1f}%)")
    print(f"Learning Capability Fitness: {learning_fitness:.2f} ({learning_fitness*100:.1f}%)")
    print(f"Security Detection Fitness: {security_fitness:.2f} ({security_fitness*100:.1f}%)")
    print(f"Overall Evolutionary Fitness: {overall_fitness:.2f} ({overall_fitness*100:.1f}%)")
    
    # Survival verdict
    if overall_fitness >= 0.8:
        verdict = "🏆 HIGHLY FIT - Strong survivor, good evolution potential"
    elif overall_fitness >= 0.6:
        verdict = "✅ FIT - Viable survivor with room for improvement"
    elif overall_fitness >= 0.4:
        verdict = "⚠️ MARGINAL - Needs significant adaptation to survive"
    else:
        verdict = "❌ UNFIT - Major evolution required for survival"
    
    print(f"\nEvolutionary Verdict: {verdict}")
    
    # Specific weaknesses discovered
    print("\n🔍 WEAKNESSES DISCOVERED (Natural Selection Pressure Points):")
    
    if quality_fitness < 0.8:
        print("  🧬 Quality assessment still has biases and edge cases")
    
    if learning_fitness < 1.0:
        print("  🧬 Memory system doesn't effectively improve suggestions")
    
    if security_fitness < 0.8:
        print("  🧬 Security detection has significant gaps")
    
    # Adaptive recommendations
    print("\n🔄 EVOLUTIONARY ADAPTATIONS NEEDED:")
    print("  🧬 Add more sophisticated security pattern recognition")
    print("  🧬 Improve logic bug detection (type errors, null refs, etc.)")
    print("  🧬 Add performance impact analysis")
    print("  🧬 Better semantic understanding beyond syntax")
    print("  🧬 Context-aware recommendations based on project type")
    
    # Final Darwin quote
    print("\n📜 Darwin's Wisdom:")
    print("  'It is not the strongest that survives, but the most adaptable.'")
    print("  This MCP server shows promise but needs continued evolution.")
    
    # Cleanup
    memory_manager.conn.close()
    try:
        os.remove(test_db)
    except:
        pass
    
    # Save detailed report
    report.update({
        "quality_detection_results": quality_detection_results,
        "learning_test": {
            "before_recommendations": before_recommendations,
            "after_recommendations": after_recommendations,
            "improved": learning_improved
        },
        "security_detection": {
            "detected": security_detection_count,
            "total": len(security_tests),
            "rate": security_fitness
        },
        "fitness_scores": {
            "quality": quality_fitness,
            "learning": learning_fitness,
            "security": security_fitness,
            "overall": overall_fitness
        },
        "evolutionary_verdict": verdict
    })
    
    report_file = f"darwin_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Detailed report saved to: {report_file}")
    
    return report


if __name__ == "__main__":
    generate_darwin_analysis_report()
