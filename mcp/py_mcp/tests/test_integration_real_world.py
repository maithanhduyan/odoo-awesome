#!/usr/bin/env python3
"""
Real-world Integration Tests for Python Code Quality MCP Server
Kiểm tra server với các trường hợp thực tế và so sánh với human expertise
"""

import unittest
import os
import tempfile
import shutil
import asyncio
import time
import json
from typing import Dict, List, Any
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from server import (
    ConfigManager, ChromaDBManager, MCPMiddleware, 
    CodeMemoryManager, EnhancedCodeAnalyzer, PythonCodeQualityServer
)


class TestRealWorldScenarios(unittest.TestCase):
    """Test với real-world code scenarios"""
    
    def setUp(self):
        self.test_db = tempfile.mktemp(suffix=".db")
        self.config = ConfigManager()
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_django_view_code_quality(self):
        """Test: Django view với common patterns"""
        django_code = """
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

@csrf_exempt
def user_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user = User.objects.create(
            name=data['name'],
            email=data['email']
        )
        return JsonResponse({'id': user.id})
    else:
        users = User.objects.all()
        return JsonResponse({'users': [u.name for u in users]})
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(django_code)
        
        # Django code should detect some issues: no validation, no error handling
        self.assertTrue(analysis["has_errors"], "Django code should detect validation issues")
        
        # But should have decent quality score for structure
        self.assertGreater(analysis["quality_score"], 40.0, "Django code should have reasonable structure score")
        
        print(f"Django view quality: {analysis['quality_score']}")
        print(f"Detected issues: {len(analysis['errors'])}")
    
    def test_data_science_notebook_code(self):
        """Test: Data science code với pandas/numpy"""
        ds_code = """
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

def analyze_dataset(file_path):
    # Load data
    df = pd.read_csv(file_path)
    
    # Basic analysis
    print(df.shape)
    print(df.describe())
    
    # Handle missing values
    df = df.dropna()
    
    # Feature engineering
    X = df.drop('target', axis=1)
    y = df['target']
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
    
    return X_train, X_test, y_train, y_test
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(ds_code)
        
        # DS code might have some issues (no error handling for file operations)
        print(f"Data Science code quality: {analysis['quality_score']}")
        print(f"Issues: {[e['message'] for e in analysis['errors']]}")
        
        # Should detect file operation issues
        file_errors = [e for e in analysis['errors'] if 'file' in e['message'].lower()]
        self.assertGreater(len(file_errors), 0, "Should detect file operation issues")
    
    def test_api_server_code(self):
        """Test: FastAPI server code"""
        fastapi_code = """
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import uvicorn

app = FastAPI()

class User(BaseModel):
    name: str
    email: str
    age: int

users_db = []

@app.post("/users/", response_model=User)
async def create_user(user: User):
    if user.age < 0:
        raise HTTPException(status_code=400, detail="Age cannot be negative")
    users_db.append(user)
    return user

@app.get("/users/", response_model=List[User])
async def get_users():
    return users_db

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(fastapi_code)
        
        # FastAPI code should be pretty good
        self.assertGreater(analysis["quality_score"], 70.0, "FastAPI code should have good quality")
        
        print(f"FastAPI server quality: {analysis['quality_score']}")
        print(f"Issues: {[e['message'] for e in analysis['errors']]}")


class TestHumanExpertComparison(unittest.TestCase):
    """So sánh kết quả server với human expert judgment"""
    
    def setUp(self):
        self.test_db = tempfile.mktemp(suffix=".db")
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_expert_vs_server_security_issues(self):
        """Test: So sánh server detection vs expert knowledge về security"""
        
        # Code với security issues mà expert sẽ bắt được
        security_vulnerable_code = """
import os
import subprocess

def execute_command(user_input):
    # SECURITY ISSUE: Command injection
    result = os.system(f"ls {user_input}")
    return result

def read_user_file(filename):
    # SECURITY ISSUE: Path traversal
    with open(f"/uploads/{filename}", 'r') as f:
        return f.read()

def unsafe_pickle_load(data):
    # SECURITY ISSUE: Pickle deserialization
    import pickle
    return pickle.loads(data)
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(security_vulnerable_code)
        
        # Expert judgment: this code has critical security issues
        expert_score = 20.0  # Expert would rate this very low
        
        print(f"Expert judgment: {expert_score}")
        print(f"Server score: {analysis['quality_score']}")
        
        # Server should detect some issues but might miss security implications
        self.assertLess(analysis["quality_score"], 60.0, "Server should detect issues in vulnerable code")
        
        # Check if server detected os.system usage
        os_errors = [e for e in analysis['errors'] if 'os.system' in e.get('message', '').lower()]
        print(f"Server detected os.system issues: {len(os_errors)}")
    
    def test_expert_vs_server_performance_issues(self):
        """Test: So sánh về performance issues"""
        
        # Code với performance issues
        performance_bad_code = """
def find_duplicates(large_list):
    duplicates = []
    for i, item in enumerate(large_list):
        for j, other_item in enumerate(large_list):
            if i != j and item == other_item and item not in duplicates:
                duplicates.append(item)
    return duplicates

def inefficient_search(data, target):
    # O(n) search in unsorted list when could use dict/set
    for item in data:
        if item == target:
            return True
    return False

def memory_wasteful_function():
    # Creates unnecessary large objects
    huge_list = [i for i in range(1000000)]
    return len(huge_list)
"""
        
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        analysis = analyzer.analyze_with_context(performance_bad_code)
        
        expert_score = 30.0  # Expert: bad performance, but structurally ok
        
        print(f"Performance code - Expert: {expert_score}, Server: {analysis['quality_score']}")
        
        # Server might not catch performance issues as well as experts
        # This is a known limitation
        print(f"Server detected issues: {[e['type'] for e in analysis['errors']]}")


class TestServerEvolution(unittest.TestCase):
    """Test khả năng học và evolution của server"""
    
    def setUp(self):
        self.test_db = tempfile.mktemp(suffix=".db")
        
    def tearDown(self):
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_learning_from_corrections(self):
        """Test: Server có học được từ corrections không?"""
        memory_manager = CodeMemoryManager(self.test_db)
        analyzer = EnhancedCodeAnalyzer(memory_manager)
        
        # Original "bad" code
        bad_code = """
def process_data(data):
    result = []
    for item in data:
        result.append(item * 2)
    return result
"""
        
        # "Good" corrected version
        good_code = """
def process_data(data: List[int]) -> List[int]:
    '''Process data by doubling each element'''
    return [item * 2 for item in data]
"""
        
        # Teach server the improvement
        memory_manager.add_code_context(bad_code, good_code, 90.0, [
            {"type": "list_comprehension", "code": "[item * 2 for item in data]"},
            {"type": "type_hints", "code": "data: List[int] -> List[int]"},
            {"type": "docstring", "code": "'''Process data by doubling each element'''"}
        ])
        
        # Test with similar bad code
        similar_bad_code = """
def double_numbers(nums):
    doubled = []
    for num in nums:
        doubled.append(num * 2)
    return doubled
"""
        
        analysis = analyzer.analyze_with_context(similar_bad_code)
        
        # Server should suggest improvements based on learned patterns
        recommendations = analysis.get("recommendations", [])
        
        print(f"Learned patterns applied: {len(recommendations)}")
        for rec in recommendations:
            print(f"- {rec}")
        
        # Should have some recommendations
        self.assertGreater(len(recommendations), 0, "Server should provide recommendations based on learning")
    
    def test_context_window_management(self):
        """Test: Context window có được quản lý hiệu quả không?"""
        memory_manager = CodeMemoryManager(self.test_db)
        
        # Add many contexts to test window management
        for i in range(50):
            code = f"def func_{i}(): return {i}"
            memory_manager.add_code_context(code, code, 80.0 + i % 20, [f"pattern_{i % 5}"])
        
        # Check memory insights
        insights = memory_manager.get_context_insights()
        
        print(f"Memory insights: {insights}")
        
        # Memory should be managed efficiently
        self.assertLess(insights["memory_size"], 100, "Memory window should be bounded")
        self.assertEqual(insights["total_contexts"], 50, "All contexts should be stored in DB")


if __name__ == "__main__":
    unittest.main()
