#!/usr/bin/env python3
"""
Python Code Quality MCP Server
Theo config.json: ChromaDB + MCP workflow cho Python code quality
Workflow: VSCode → MCP → Phát hiện lỗi → ChromaDB → Context → LLM → Safe Code
"""

import asyncio
import json
import sys
import ast
import re
import os
from typing import Any, Dict, List, Optional
from pathlib import Path
import logging
import hashlib
from datetime import datetime
from collections import defaultdict, deque
import pickle
import sqlite3

# Import ChromaDB (optional - sẽ fallback nếu không có)
try:
    import chromadb
    from chromadb.utils import embedding_functions
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False


class ConfigManager:
    """Quản lý cấu hình từ config.json"""
    
    def __init__(self, config_path: str = "../config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self._setup_logging()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load config từ file"""
        try:
            # Tìm config.json từ src/ directory
            current_dir = Path(__file__).parent
            config_file = current_dir.parent / "config.json"
            
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Default config nếu không tìm thấy file
                return {
                    "chromadb_path": "./py_mcp/chroma_db",
                    "log_level": "INFO",
                    "server": {
                        "name": "python-code-quality",
                        "version": "0.2.0",
                        "description": "MCP Server for Python code quality"
                    }
                }
        except Exception as e:
            print(f"Warning: Could not load config.json: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Default config fallback"""
        return {
            "chromadb_path": "./py_mcp/chroma_db",
            "log_level": "INFO",
            "server": {
                "name": "python-code-quality",
                "version": "0.2.0",
                "description": "MCP Server for Python code quality"
            }
        }
    
    def _setup_logging(self):
        """Setup logging theo config"""
        log_level = getattr(logging, self.config.get("log_level", "INFO"))
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        global logger
        logger = logging.getLogger(__name__)
        if not HAS_CHROMADB:
            logger.warning("ChromaDB not available - using mock implementation")
    
    def get(self, key: str, default=None):
        """Get config value"""
        return self.config.get(key, default)


class CodeAnalyzer:
    """Phát hiện lỗi code Python theo workflow - Bước C"""
    
    def __init__(self):
        self.error_patterns = {
            'division_by_zero': {
                'regex': r'\/\s*0(?![.\d])',
                'severity': 'high',
                'description': 'Potential division by zero'
            },
            'no_exception_handling': {
                'regex': r'open\s*\([^)]*\)(?![^{]*except)',
                'severity': 'medium', 
                'description': 'File operation without exception handling'
            },
            'eval_usage': {
                'regex': r'\beval\s*\(',
                'severity': 'critical',
                'description': 'Dangerous eval() usage'
            },
            'bare_except': {
                'regex': r'except\s*:',
                'severity': 'medium',
                'description': 'Bare except clause'
            }
        }
    
    def analyze_code(self, code: str) -> Dict[str, Any]:
        """
        Bước C: Phát hiện lỗi trong code Python
        Returns: {"has_errors": bool, "errors": List, "analysis": Dict}
        """
        errors = []
        
        # Phân tích AST để check syntax
        try:
            ast.parse(code)
            syntax_valid = True
        except SyntaxError as e:
            errors.append({
                'type': 'syntax_error',
                'severity': 'critical',
                'description': f'Syntax error: {str(e)}',
                'line': e.lineno
            })
            syntax_valid = False
        
        # Phân tích patterns để tìm lỗi thường gặp
        for error_type, pattern_info in self.error_patterns.items():
            matches = re.finditer(pattern_info['regex'], code)
            for match in matches:
                line_num = code[:match.start()].count('\n') + 1
                errors.append({
                    'type': error_type,
                    'severity': pattern_info['severity'],
                    'description': pattern_info['description'],
                    'line': line_num,
                    'match': match.group()
                })
        
        return {
            "has_errors": len(errors) > 0,
            "syntax_valid": syntax_valid,
            "errors": errors,
            "analysis": {
                "total_errors": len(errors),
                "critical_errors": len([e for e in errors if e['severity'] == 'critical']),
                "code_length": len(code.split('\n'))
            }
        }


class ChromaDBManager:
    """Bước D: Query ChromaDB để lấy safe patterns"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.has_chromadb = HAS_CHROMADB
        self.safe_patterns = self._get_mock_patterns()
        
        if self.has_chromadb:
            try:
                db_path = self.config.get("chromadb_path", "./py_mcp/chroma_db")
                # Expand workspace folder nếu có
                if "${workspaceFolder}" in db_path:
                    workspace = Path(__file__).parent.parent.parent
                    db_path = db_path.replace("${workspaceFolder}", str(workspace))
                
                self.client = chromadb.PersistentClient(path=db_path)
                self.collection = self.client.get_or_create_collection(
                    name="python_safe_patterns"
                )
                self._ensure_seeded()
                logger.info(f"ChromaDB initialized at: {db_path}")
            except Exception as e:
                logger.warning(f"ChromaDB init failed: {e}, using mock patterns")
                self.has_chromadb = False
    
    def _get_mock_patterns(self) -> Dict[str, str]:
        """Mock safe patterns khi không có ChromaDB"""
        return {
            'division_by_zero': '''
# Safe division pattern
def safe_divide(numerator, denominator):
    try:
        return numerator / denominator
    except ZeroDivisionError:
        return float('inf') if numerator > 0 else float('-inf')
''',
            'no_exception_handling': '''
# Safe file handling pattern
def safe_read_file(filename):
    try:
        with open(filename, 'r') as file:
            return file.read()
    except FileNotFoundError:
        return ""
    except PermissionError:
        return ""
''',
            'eval_usage': '''
# Safe alternative to eval
import ast
def safe_eval(expression):
    try:
        return ast.literal_eval(expression)
    except (ValueError, SyntaxError):
        return None
''',
            'bare_except': '''
# Specific exception handling
try:
    risky_operation()
except SpecificException as e:
    logger.error(f"Specific error: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
'''
        }
    
    def _ensure_seeded(self):
        """Seed ChromaDB với safe patterns"""
        if not self.has_chromadb or self.collection.count() > 0:
            return
        
        patterns = [
            {
                "id": f"safe_{error_type}",
                "document": pattern,
                "metadata": {"type": error_type, "safety": "high"}
            }
            for error_type, pattern in self.safe_patterns.items()
        ]
        
        self.collection.add(
            documents=[p["document"] for p in patterns],
            metadatas=[p["metadata"] for p in patterns],
            ids=[p["id"] for p in patterns]
        )
    
    def query_safe_patterns(self, error_types: List[str]) -> List[str]:
        """Query safe patterns cho error types"""
        patterns = []
        
        # Lấy patterns từ mock data trước
        for error_type in error_types:
            if error_type in self.safe_patterns:
                patterns.append(self.safe_patterns[error_type])
        
        # Nếu có ChromaDB, query thêm
        if self.has_chromadb and error_types:
            try:
                results = self.collection.query(
                    query_texts=[" ".join(error_types)],
                    n_results=min(3, len(error_types))
                )
                if results and results.get('documents') and results['documents'][0]:
                    patterns.extend(results['documents'][0])
            except Exception as e:
                logger.warning(f"ChromaDB query failed: {e}")
        
        return patterns[:3]  # Giới hạn 3 patterns


class MCPMiddleware:
    """Bước E: Tái cấu trúc Context cho LLM"""
    
    def __init__(self, chroma_manager: ChromaDBManager, config: ConfigManager):
        self.chroma = chroma_manager
        self.config = config
        self.analyzer = CodeAnalyzer()
    
    def create_mcp_context(self, code: str, errors: List[Dict], safe_patterns: List[str]) -> Dict[str, Any]:
        """Bước E: Tái cấu trúc context theo chuẩn MCP"""
        return {
            "version": "mcp-1.0",
            "server": self.config.get("server", {}),
            "context": {
                "original_code": code,
                "detected_issues": errors,
                "safe_patterns": safe_patterns,
                "project_info": {
                    "language": "python",
                    "safety_level": "high"
                }
            },
            "prompt": "Fix the detected issues using safe patterns provided",
            "constraints": [
                "Always include error handling",
                "Follow PEP8 guidelines", 
                "Use safe alternatives to dangerous functions",
                "Maintain original functionality"
            ],
            "metadata": {
                "workflow": "VSCode→MCP→ChromaDB→LLM",
                "timestamp": "2025-06-14"
            }
        }
    
    def generate_safe_code(self, original_code: str, mcp_context: Dict) -> str:
        """
        Bước F: Mock LLM để generate safe code
        Trong thực tế sẽ gọi OpenAI/Claude API với mcp_context
        """
        errors = mcp_context["context"]["detected_issues"]
        improved_code = original_code
        
        for error in errors:
            error_type = error['type']
            
            if error_type == 'division_by_zero':
                improved_code = self._fix_division(improved_code)
            elif error_type == 'no_exception_handling':
                improved_code = self._fix_file_ops(improved_code)
            elif error_type == 'eval_usage':
                improved_code = improved_code.replace('eval(', 'ast.literal_eval(')
                if 'import ast' not in improved_code:
                    improved_code = 'import ast\n' + improved_code
            elif error_type == 'bare_except':
                improved_code = self._fix_bare_except(improved_code)
        
        return improved_code
    
    def _fix_division(self, code: str) -> str:
        """Fix division by zero"""
        if 'try:' not in code and '/' in code:
            lines = code.split('\n')
            indented_lines = ['try:'] + ['    ' + line for line in lines] + [
                'except ZeroDivisionError:',
                '    print("Warning: Division by zero avoided")',
                '    result = float("inf")'
            ]
            return '\n'.join(indented_lines)
        return code
    
    def _fix_file_ops(self, code: str) -> str:
        """Fix file operations"""
        if 'open(' in code and 'with' not in code:
            # Simple replacement - trong thực tế cần parser phức tạp hơn
            lines = code.split('\n')
            fixed_lines = []
            for line in lines:
                if 'open(' in line and 'with' not in line:
                    # Wrap với with statement
                    indent = len(line) - len(line.lstrip())
                    fixed_lines.append(' ' * indent + 'try:')
                    fixed_lines.append(' ' * (indent + 4) + 'with ' + line.strip())
                    fixed_lines.append(' ' * (indent + 8) + '# File operations here')
                    fixed_lines.append(' ' * indent + 'except (FileNotFoundError, PermissionError):')
                    fixed_lines.append(' ' * (indent + 4) + 'pass  # Handle file errors')
                else:
                    fixed_lines.append(line)
            return '\n'.join(fixed_lines)
        return code
    
    def _fix_bare_except(self, code: str) -> str:
        """Fix bare except clauses"""
        return code.replace('except:', 'except Exception as e:')


class EnhancedCodeAnalyzer(CodeAnalyzer):
    """Phát hiện lỗi code Python với context và memory awareness"""
    
    def __init__(self, memory_manager):
        super().__init__()
        self.memory_manager = memory_manager
    
    def analyze_with_context(self, code: str) -> Dict[str, Any]:
        """
        Phân tích code với context và memory
        Returns: {"has_errors": bool, "errors": List, "analysis": Dict, "quality_score": float, "similar_contexts": List}
        """
        analysis = self.analyze_code(code)
        errors = analysis["errors"]
        
        # Tính toán quality score dựa trên memory patterns
        quality_score = self._calculate_quality_score(code)
        
        # Tìm các context tương tự từ memory
        similar_contexts = self._find_similar_contexts(code, quality_score)
        
        # Gợi ý cải thiện dựa trên patterns và context tương tự
        recommendations = self._generate_recommendations(similar_contexts, quality_score)
        
        return {            **analysis,
            "quality_score": quality_score,
            "similar_contexts": similar_contexts,
            "recommendations": recommendations
        }
    
    def _calculate_quality_score(self, code: str) -> float:
        """Tính toán quality score cho code với nhiều tiêu chí"""
        # Base score
        base_score = 50.0
        readability_score = 0.0
        performance_score = 0.0
        safety_score = 0.0
        
        # 1. Readability factors
        if '"""' in code or "'''" in code:  # Docstrings
            readability_score += 15.0
        if 'def ' in code and '(' in code and ':' in code:  # Type hints
            if '->' in code:
                readability_score += 10.0
        if len(code.split('\n')) > 1:  # Multi-line structure
            readability_score += 5.0
        if '# ' in code:  # Comments
            readability_score += 5.0
        
        # 2. Performance factors (can conflict with readability)
        if '@functools.lru_cache' in code:
            performance_score -= 5.0  # Caching có thể chậm với small operations
        if 'recursion' in code.lower() or 'recursive' in code.lower():
            performance_score -= 10.0  # Recursion có thể chậm
        if 'for _ in range(' in code:  # Efficient loops
            performance_score += 10.0
        if 'a, b = b, a' in code:  # Efficient swapping
            performance_score += 5.0
        
        # 3. Safety factors
        for error in self.analyze_code(code)["errors"]:
            if error["severity"] == "critical":
                safety_score -= 30.0
            elif error["severity"] == "high":
                safety_score -= 15.0
            elif error["severity"] == "medium":
                safety_score -= 5.0
        
        # Final calculation - biased toward readability over performance
        total_score = base_score + readability_score * 0.6 + performance_score * 0.3 + safety_score
        
        return max(0.0, min(100.0, total_score))
    
    def _find_similar_contexts(self, code: str, quality_score: float) -> List[Dict]:
        """Tìm các context tương tự từ memory"""
        similar = []
        
        for context in self.memory_manager.context_window:
            if context["score"] < quality_score - 10:
                continue  # Bỏ qua các context kém hơn 10 điểm
            
            # So sánh nội dung code (giả định là code tương tự nếu cùng chứa các hàm và biến chính)
            if self._is_similar_code(code, context["code"]):
                similar.append(context)
        
        return similar
    
    def _is_similar_code(self, code1: str, code2: str) -> bool:
        """Kiểm tra hai đoạn code có tương tự nhau không"""
        # So sánh số lượng hàm và biến chính
        def extract_functions(code: str):
            return re.findall(r'def\s+(\w+)\s*\(', code)
        
        def extract_variables(code: str):
            return re.findall(r'\b(\w+)\s*=', code)
        
        funcs1, vars1 = extract_functions(code1), extract_variables(code1)
        funcs2, vars2 = extract_functions(code2), extract_variables(code2)
        
        return len(set(funcs1) & set(funcs2)) > 0 or len(set(vars1) & set(vars2)) > 0
    
    def _generate_recommendations(self, similar_contexts: List[Dict], quality_score: float) -> List[Dict]:
        """Gợi ý cải thiện dựa trên các context tương tự"""
        recommendations = []
        
        for context in similar_contexts:
            if context["score"] < quality_score - 5:
                continue  # Bỏ qua nếu context kém hơn 5 điểm
            
            # Gợi ý thêm exception handling nếu context có xử lý ngoại lệ tốt
            if "try:" in context["code"] and "except:" in context["code"]:
                recommendations.append({
                    "type": "no_exception_handling",
                    "code": context["code"],
                    "reason": "Context has good exception handling"
                })
            
            # Gợi ý sử dụng with statement cho file operations
            if "open(" in context["code"] and "with" in context["code"]:
                recommendations.append({
                    "type": "file_handling",
                    "code": context["code"],
                    "reason": "Context uses with statement for file handling"
                })
        
        return recommendations


class CodeMemoryManager:
    """Quản lý bộ nhớ code và patterns chất lượng cao"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.context_window = deque(maxlen=50)  # 50 context gần nhất
        self.quality_patterns = []
        
        # Kết nối SQLite để lưu trữ patterns và context
        self.conn = sqlite3.connect(self.db_path)
        self._init_db()
    
    def _init_db(self):
        """Khởi tạo cơ sở dữ liệu"""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS code_history (
                    id INTEGER PRIMARY KEY,
                    original_code TEXT,
                    safe_code TEXT,
                    quality_score REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS quality_patterns (
                    id INTEGER PRIMARY KEY,
                    pattern_type TEXT,
                    pattern_code TEXT,
                    quality_score REAL,
                    context_id INTEGER,
                    FOREIGN KEY (context_id) REFERENCES code_history (id)
                )
            """)
    
    def add_code_context(self, original_code: str, safe_code: str, quality_score: float, patterns: List[str]):
        """Thêm context code vào bộ nhớ"""
        with self.conn:
            cursor = self.conn.execute("""
                INSERT INTO code_history (original_code, safe_code, quality_score)
                VALUES (?, ?, ?)
            """, (original_code, safe_code, quality_score))
            
            context_id = cursor.lastrowid
              # Thêm các patterns chất lượng cao liên quan
            for pattern in patterns:
                if isinstance(pattern, dict):
                    self.conn.execute("""
                        INSERT INTO quality_patterns (pattern_type, pattern_code, quality_score, context_id)
                        VALUES (?, ?, ?, ?)
                    """, (pattern["type"], pattern["code"], quality_score, context_id))
                else:
                    # Pattern là string đơn giản
                    self.conn.execute("""
                        INSERT INTO quality_patterns (pattern_type, pattern_code, quality_score, context_id)
                        VALUES (?, ?, ?, ?)
                    """, (str(pattern), "", quality_score, context_id))
            
            # Cập nhật bộ nhớ
            self.context_window.append({
                "id": context_id,
                "code": original_code,
                "safe_code": safe_code,
                "score": quality_score,
                "patterns": patterns
            })
    
    def learn_quality_pattern(self, pattern_type: str, pattern_code: str, quality_score: float):
        """Học một pattern chất lượng cao mới"""
        with self.conn:
            self.conn.execute("""
                INSERT INTO quality_patterns (pattern_type, pattern_code, quality_score)
                VALUES (?, ?, ?)
            """, (pattern_type, pattern_code, quality_score))
            
            # Cập nhật bộ nhớ
            self.quality_patterns.append({
                "type": pattern_type,
                "code": pattern_code,
                "score": quality_score
            })
    
    def get_quality_recommendations(self, pattern_types: List[str]) -> List[Dict]:
        """Lấy recommendations dựa trên pattern types"""
        recommendations = []
        
        cursor = self.conn.execute("""
            SELECT pattern_type, pattern_code, quality_score, COUNT(*) as frequency
            FROM quality_patterns 
            WHERE pattern_type IN ({})
            GROUP BY pattern_type, pattern_code
            ORDER BY frequency DESC, quality_score DESC
            LIMIT 10
        """.format(','.join(['?' for _ in pattern_types])), pattern_types)
        
        for row in cursor.fetchall():
            recommendations.append({
                "type": row[0],
                "code": row[1],
                "score": row[2],
                "frequency": row[3],
                "recommendation": f"Consider pattern '{row[0]}' with score {row[2]}"
            })
        
        return recommendations
    
    def get_similar_contexts(self, code: str, similarity_threshold: float = 0.7) -> List[Dict]:
        """Tìm các contexts tương tự với code đã cho"""
        similar = []
        
        # Simple similarity based on common keywords and structure
        code_keywords = set(re.findall(r'\b\w+\b', code.lower()))
        
        cursor = self.conn.execute("""
            SELECT id, original_code, safe_code, quality_score
            FROM code_history
            ORDER BY quality_score DESC
            LIMIT 50
        """)
        
        for row in cursor.fetchall():
            context_keywords = set(re.findall(r'\b\w+\b', row[1].lower()))
            
            # Calculate Jaccard similarity
            intersection = len(code_keywords.intersection(context_keywords))
            union = len(code_keywords.union(context_keywords))
            similarity = intersection / union if union > 0 else 0
            
            if similarity >= similarity_threshold:
                similar.append({
                    "id": row[0],
                    "original_code": row[1],
                    "safe_code": row[2],
                    "quality_score": row[3],
                    "similarity": similarity
                })
        
        return sorted(similar, key=lambda x: x["similarity"], reverse=True)
    
    def get_context_insights(self) -> Dict[str, Any]:
        """Lấy thống kê và insights từ memory"""
        cursor = self.conn.execute("""
            SELECT COUNT(*) as total_contexts, 
                   AVG(quality_score) as avg_quality,
                   MAX(quality_score) as max_quality,
                   MIN(quality_score) as min_quality
            FROM code_history
        """)
        
        stats = cursor.fetchone()
        
        # Pattern statistics
        pattern_cursor = self.conn.execute("""
            SELECT pattern_type, COUNT(*) as count, AVG(quality_score) as avg_score
            FROM quality_patterns
            GROUP BY pattern_type
            ORDER BY count DESC
        """)
        
        pattern_stats = []
        for row in pattern_cursor.fetchall():
            pattern_stats.append({
                "type": row[0],
                "count": row[1],
                "avg_score": row[2]
            })
        
        return {
            "total_contexts": stats[0] if stats else 0,
            "avg_quality": stats[1] if stats else 0,
            "max_quality": stats[2] if stats else 0,
            "min_quality": stats[3] if stats else 0,
            "pattern_stats": pattern_stats,
            "memory_size": len(self.context_window)
        }


class EnhancedMCPMiddleware(MCPMiddleware):
    """Enhanced MCP Middleware với memory và context awareness"""
    
    def __init__(self, chroma_manager: ChromaDBManager, config: ConfigManager, memory_manager: CodeMemoryManager):
        super().__init__(chroma_manager, config)
        self.memory_manager = memory_manager
        self.analyzer = EnhancedCodeAnalyzer(memory_manager)
    
    def create_enhanced_context(self, code: str, analysis: Dict, safe_patterns: List[str]) -> Dict[str, Any]:
        """Tạo enhanced context với memory và recommendations"""
        base_context = super().create_mcp_context(code, analysis["errors"], safe_patterns)
        
        # Add memory and context information
        enhanced_context = {
            **base_context,
            "enhanced_features": {
                "quality_score": analysis["quality_score"],
                "quality_patterns": analysis["quality_patterns"],
                "similar_contexts": analysis["similar_contexts"][:3],  # Top 3 similar contexts
                "recommendations": analysis["recommendations"],
                "context_memory_size": analysis["context_length"]
            },
            "learning_data": {
                "pattern_frequencies": dict(self.memory_manager.quality_patterns),
                "historical_improvements": len(self.memory_manager.context_window)
            }
        }
        
        return enhanced_context
    
    def generate_context_aware_code(self, original_code: str, enhanced_context: Dict) -> str:
        """Generate code với context awareness từ memory"""
        # Start with basic fixes
        improved_code = super().generate_safe_code(original_code, enhanced_context)
        
        # Apply context-based improvements
        similar_contexts = enhanced_context["enhanced_features"]["similar_contexts"]
        recommendations = enhanced_context["enhanced_features"]["recommendations"]
        
        # Learn from similar high-quality contexts
        for context in similar_contexts:
            if context.get("score", 0) > 80:  # High quality code
                # Apply patterns from high-quality similar code
                improved_code = self._apply_quality_patterns(improved_code, context)
        
        # Apply learned recommendations
        for rec in recommendations:
            if rec["quality_score"] > 75:
                improved_code = self._apply_recommendation(improved_code, rec)
        
        return improved_code
    
    def _apply_quality_patterns(self, code: str, context: Dict) -> str:
        """Apply quality patterns từ similar contexts"""
        # Example: If similar context uses type hints, suggest adding them
        if "def " in code and ":" in context["safe"] and "->" in context["safe"]:
            # Simple pattern matching for function signatures
            functions = re.findall(r'def\s+(\w+)\s*\([^)]*\):', code)
            for func_name in functions:
                if f"def {func_name}" in code and f"def {func_name}" not in code.replace(":", " -> "):
                    logger.info(f"Suggestion: Add type hints to function {func_name}")
        
        return code
    
    def _apply_recommendation(self, code: str, recommendation: Dict) -> str:
        """Apply specific recommendation"""
        rec_type = recommendation["type"]
        rec_code = recommendation["code"]
        
        if rec_type == "no_exception_handling" and "with open" in rec_code:
            # Prefer context manager pattern from recommendations
            if "open(" in code and "with" not in code:
                code = re.sub(
                    r'(\s*)(\w+)\s*=\s*open\(',
                    r'\1with open(',
                    code
                )
        
        return code


class PythonCodeQualityServer:
    """
    Enhanced MCP Server cho Python Code Quality với memory và context learning
    Workflow: VSCode → MCP → Phát hiện lỗi → ChromaDB → Context → LLM → Safe Code
    """
    
    def __init__(self):
        self.config = ConfigManager()
        server_info = self.config.get("server", {})
        
        self.name = server_info.get("name", "python-code-quality")
        self.version = server_info.get("version", "0.2.0")
        self.description = server_info.get("description", "MCP Server for Python code quality")
        
        # Initialize components theo config
        self.chroma_manager = ChromaDBManager(self.config)
          # Initialize memory manager
        db_path = "./py_mcp/code_memory.db"
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.memory_manager = CodeMemoryManager(db_path)
          # Use enhanced middleware
        self.middleware = EnhancedMCPMiddleware(self.chroma_manager, self.config, self.memory_manager)
        
        logger.info(f"Enhanced server initialized with memory at: {db_path}")
    
    async def handle_validate_code(self, arguments: Dict[str, Any]) -> str:
        """Enhanced validate_code với memory và context awareness"""
        code = arguments.get("code", "")
        if not code.strip():
            return json.dumps({"error": "No code provided"}, indent=2)
        
        try:
            # Bước C: Enhanced analysis với context
            analysis = self.middleware.analyzer.analyze_with_context(code)
            
            if not analysis["has_errors"]:
                # Vẫn học từ safe code để improve context
                quality_patterns = analysis["quality_patterns"]
                for pattern in quality_patterns:
                    self.memory_manager.learn_quality_pattern(
                        pattern["type"], pattern["code"], analysis["quality_score"]
                    )
                
                # Store in memory for future context
                self.memory_manager.add_code_context(code, code, analysis["quality_score"], [])
                
                return json.dumps({
                    "status": "safe",
                    "message": "Code is already safe - no issues detected",
                    "original_code": code,
                    "analysis": analysis["analysis"],
                    "quality_score": analysis["quality_score"],
                    "quality_patterns": analysis["quality_patterns"],
                    "context_insights": {
                        "similar_contexts_found": len(analysis["similar_contexts"]),
                        "memory_size": analysis["context_length"]
                    },
                    "server": {
                        "name": self.name,
                        "version": self.version
                    }
                }, indent=2)
            
            # Có lỗi → Enhanced workflow
            
            # Bước D: Query ChromaDB với enhanced patterns
            error_types = [error["type"] for error in analysis["errors"]]
            safe_patterns = self.chroma_manager.query_safe_patterns(error_types)
            
            # Bước E: Enhanced context creation
            enhanced_context = self.middleware.create_enhanced_context(
                code, analysis, safe_patterns
            )
            
            # Bước F: Context-aware safe code generation
            safe_code = self.middleware.generate_context_aware_code(code, enhanced_context)
            
            # Calculate improvement score
            safe_analysis = self.middleware.analyzer.analyze_with_context(safe_code)
            improvement_score = safe_analysis["quality_score"] - analysis["quality_score"]
            
            # Learn from this improvement
            if improvement_score > 0:
                self.memory_manager.add_code_context(
                    code, safe_code, safe_analysis["quality_score"], 
                    [pattern["code"] for pattern in safe_analysis["quality_patterns"]]
                )
                
                # Learn quality patterns from improved code
                for pattern in safe_analysis["quality_patterns"]:
                    self.memory_manager.learn_quality_pattern(
                        pattern["type"], pattern["code"], safe_analysis["quality_score"]
                    )
            
            # Bước G: Enhanced result
            return json.dumps({
                "status": "improved",
                "message": f"Fixed {len(analysis['errors'])} issues with {improvement_score:.1f} quality improvement",
                "original_code": code,
                "safe_code": safe_code,
                "detected_errors": analysis["errors"],
                "safe_patterns_used": len(safe_patterns),
                "enhanced_context": enhanced_context,
                "quality_analysis": {
                    "original_score": analysis["quality_score"],
                    "improved_score": safe_analysis["quality_score"],
                    "improvement": improvement_score,
                    "quality_patterns_learned": len(safe_analysis["quality_patterns"])
                },
                "context_insights": {
                    "similar_contexts_used": len(analysis["similar_contexts"]),
                    "recommendations_applied": len(analysis["recommendations"]),
                    "memory_size": analysis["context_length"]
                },
                "analysis": analysis["analysis"],
                "server": {
                    "name": self.name,
                    "version": self.version
                }
            }, indent=2)
            
        except Exception as e:
            logger.error(f"Error during enhanced validation: {e}")
            return json.dumps({"error": f"Enhanced validation failed: {str(e)}"}, indent=2)
    
    async def handle_learn_from_code(self, arguments: Dict[str, Any]) -> str:
        """New tool: Learn từ high-quality code examples"""
        code = arguments.get("code", "")
        quality_score = arguments.get("quality_score", 85.0)
        
        if not code.strip():
            return json.dumps({"error": "No code provided"}, indent=2)
        
        try:
            # Analyze quality patterns
            analysis = self.middleware.analyzer.analyze_with_context(code)
            
            # Force learning from high-quality code
            for pattern in analysis["quality_patterns"]:
                self.memory_manager.learn_quality_pattern(
                    pattern["type"], pattern["code"], quality_score
                )
            
            # Add to memory
            self.memory_manager.add_code_context(code, code, quality_score, 
                [pattern["code"] for pattern in analysis["quality_patterns"]])
            
            return json.dumps({
                "status": "learned",
                "message": f"Learned {len(analysis['quality_patterns'])} quality patterns",
                "code": code,
                "quality_score": quality_score,
                "patterns_learned": analysis["quality_patterns"],
                "memory_size": len(self.memory_manager.context_window)
            }, indent=2)
            
        except Exception as e:
            logger.error(f"Error learning from code: {e}")
            return json.dumps({"error": f"Learning failed: {str(e)}"}, indent=2)
    
    async def handle_get_context_insights(self, arguments: Dict[str, Any]) -> str:
        """New tool: Get context insights và memory statistics"""
        try:
            # Memory statistics
            total_contexts = len(self.memory_manager.context_window)
            quality_patterns_count = len(self.memory_manager.quality_patterns)
            
            # Database statistics
            cursor = self.memory_manager.conn.execute("SELECT COUNT(*) FROM code_history")
            total_history = cursor.fetchone()[0]
            
            cursor = self.memory_manager.conn.execute("SELECT AVG(quality_score) FROM code_history")
            avg_quality = cursor.fetchone()[0] or 0
            
            cursor = self.memory_manager.conn.execute("""
                SELECT pattern_type, COUNT(*), AVG(quality_score) 
                FROM quality_patterns 
                GROUP BY pattern_type 
                ORDER BY COUNT(*) DESC
            """)
            pattern_stats = cursor.fetchall()
            
            return json.dumps({
                "context_insights": {
                    "active_memory_size": total_contexts,
                    "total_code_history": total_history,
                    "average_quality_score": round(avg_quality, 2),
                    "quality_patterns_learned": quality_patterns_count,
                    "pattern_statistics": [
                        {
                            "type": row[0],
                            "count": row[1], 
                            "avg_quality": round(row[2], 2)
                        } for row in pattern_stats
                    ]
                },
                "memory_status": "active",
                "learning_capacity": "50 recent contexts + unlimited history"
            }, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting context insights: {e}")
            return json.dumps({"error": f"Context insights failed: {str(e)}"}, indent=2)
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Xử lý request theo JSON-RPC 2.0"""
        try:
            method = request.get("method")
            params = request.get("params", {})
            req_id = request.get("id")

            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": self.name,
                            "version": self.version
                        }
                    }
                }

            elif method == "tools/list":
                tools = [
                    {
                        "name": "validate_code",
                        "description": f"{self.description} - Enhanced validation with memory and context learning",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string", "description": "Python code to validate and improve"}
                            },
                            "required": ["code"]
                        }
                    },
                    {
                        "name": "learn_from_code",
                        "description": "Learn quality patterns from high-quality code examples",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "code": {"type": "string", "description": "High-quality Python code to learn from"},
                                "quality_score": {"type": "number", "description": "Quality score (0-100)", "default": 85.0}
                            },
                            "required": ["code"]
                        }
                    },
                    {
                        "name": "get_context_insights",
                        "description": "Get memory and context learning insights",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                ]
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": tools}
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if tool_name == "validate_code":
                    result = await self.handle_validate_code(arguments)
                elif tool_name == "learn_from_code":
                    result = await self.handle_learn_from_code(arguments)
                elif tool_name == "get_context_insights":
                    result = await self.handle_get_context_insights(arguments)
                else:
                    raise ValueError(f"Unknown tool: {tool_name}")

                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": result}]
                    }
                }

            else:
                raise ValueError(f"Unknown method: {method}")

        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }

    async def run_stdio(self):
        """Chạy server qua STDIO"""
        logger.info(f"Python Code Quality MCP Server {self.name} v{self.version} started")
        logger.info(f"Description: {self.description}")
        logger.info(f"ChromaDB available: {self.chroma_manager.has_chromadb}")

        try:
            while True:
                line = sys.stdin.readline()
                if not line:
                    break

                try:
                    request = json.loads(line.strip())
                    response = await self.handle_request(request)

                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()

                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": "Parse error"
                        }
                    }
                    sys.stdout.write(json.dumps(error_response) + "\n")
                    sys.stdout.flush()

        except KeyboardInterrupt:
            logger.info("Server stopped")
        except Exception as e:
            logger.error(f"Server error: {e}")


async def main():
    """Entry point chính theo config.json với enhanced features"""
    server = PythonCodeQualityServer()
    await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
