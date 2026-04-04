# Python Model Context Protocol (MCP)

## Sử dụng ChromaDB và ModelContextProtocol
- ChromaDB lưu trữ các code python chất lượng cao
- ModelContextProtocol giao tiếp với ai để giúp sản xuất code chất lượng cao
🧠 Model Context Protocol (MCP) là gì?
MCP (Model Context Protocol) là một chuẩn hóa giao diện giữa agent (như Copilot) và mô hình LLM, cho phép truyền và truy vấn context (ngữ cảnh) một cách có cấu trúc, mở rộng được, để: Giảm rủi ro context quá dài (tràn token). Tối ưu truy vấn với dữ liệu ngữ nghĩa. Cho phép hệ thống "ghi nhớ" lâu dài bằng memory store như ChromaDB


## 🎯Mục tiêu: Kết hợp MCP + ChromaDB để cải thiện Copilot Agent
Dùng ChromaDB làm bộ nhớ (memory store) cho lập trình viên Python là một cách tiếp cận phổ biến khi bạn muốn xây dựng các hệ thống trí tuệ nhân tạo có khả năng ghi nhớ và truy xuất thông tin theo ngữ nghĩa (semantic search). Đây là một hướng dẫn ngắn gọn để bạn triển khai ChromaDB trong Python
Khi Copilot sinh code sai, hệ thống có thể:

Truy vấn lại context thông minh từ ChromaDB (bộ nhớ vector)
Tái cấu trúc context đầu vào cho LLM theo chuẩn MCP
Tối ưu prompt để LLM tạo ra mã đúng cú pháp và đúng logic hơn
- Giúp VSCode Copilot Agent viết mã Python tránh sai cú pháp, ta hoàn toàn có thể giảm sai sót và tăng chất lượng mã bằng cách kết hợp  MCP (Multi-Code Prompting) + ChromaDB

## 🏗️ Cấu trúc hệ thống:

## Use Case
✨ Use Case cụ thể
User viết mã bị lỗi chia cho 0

Copilot Agent sinh ra mã chưa xử lý lỗi

MCP phân tích: phát hiện lỗi tiềm tàng

Truy vấn ChromaDB tìm mã chia có try/except

MCP tái cấu trúc prompt + context

LLM sinh ra mã hoàn chỉnh, đúng cú pháp và an toàn

##  Bạn có thể làm gì với điều này trong thực tế?
Tích hợp ChromaDB với VSCode Copilot Agent qua middleware dùng chuẩn MCP

Thiết kế format MCP JSON tự động từ project structure

Đào tạo ChromaDB bằng dữ liệu thực tế (codebase, lỗi thường gặp)

Dùng semantic similarity để chọn context "tốt nhất" mỗi lần Copilot gửi request tới GPT

## 🚀 Quick Setup

### 1. Configuration
Copy the example config and customize:
```bash
cp config.example.json config.json
# Edit config.json with your settings
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize Database
The server will automatically create ChromaDB and SQLite databases on first run.

### 4. Run Tests
```bash
# Run all comprehensive tests
python tests/run_all_tests.py

# Run specific test suites
python -m pytest tests/test_server_challenges.py -v
python -m pytest tests/test_performance_stress.py -v

# Quick capability check
python tests/quick_test_summary.py

# Darwin evolutionary analysis
python tests/darwin_final_analysis.py
```

### 5. Start Server
```bash
python src/server.py
```

## 🧬 Test Results Summary

### Latest Test Results (June 14, 2025):
- ✅ **Basic Functionality**: 100% (All core features working)
- ⚠️ **Security Detection**: 40% (Needs improvement)
- ⚠️ **Quality Scoring**: 67% (Some bias issues)
- ❌ **Memory Learning**: 0% (Learning system needs work)
- ✅ **Edge Cases**: 100% (Robust handling)
- ✅ **Performance**: 100% (No crashes under stress)

**Overall Darwin Fitness: 35.6% (UNFIT for production)**

See `tests/COMPREHENSIVE_TEST_REPORT.md` for detailed analysis.

## 📁 Files to Ignore (Already in .gitignore)

These files contain sensitive data or temporary content:
- `config.json` - Contains API keys and settings
- `code_memory.db` - SQLite database with learned patterns
- `chroma_db/` - ChromaDB vector database
- `test_report_*.json` - Test result files
- `darwin_analysis_*.json` - Analysis reports

## 🔧 Development

### Key Components:
- `src/server.py` - Main MCP server with enhanced analysis
- `src/` - Core server implementation
- `tests/` - Comprehensive test suite with Darwin methodology
- `config.example.json` - Configuration template

### Testing Philosophy:
This project uses **Darwin-style testing** - challenging every assumption and falsifying hypotheses to ensure robustness.