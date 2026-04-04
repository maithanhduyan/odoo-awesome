# PostgreSQL MCP Server (HTTP)

Một Model Context Protocol (MCP) server sử dụng HTTP API để kết nối và truy vấn PostgreSQL database.

## Tính năng

- ✅ Kết nối đến PostgreSQL server
- ✅ Đếm số lượng database
- ✅ Liệt kê tất cả database  
- ✅ Liệt kê schema trong database
- ✅ Liệt kê table trong schema
- ✅ Xem cấu trúc chi tiết của table (columns, data types, primary keys, foreign keys)
- ✅ Xem dữ liệu từ table với limit
- ✅ Thực thi SQL query tùy chỉnh (chỉ SELECT để đảm bảo an toàn)
- ✅ HTTP API với FastAPI
- ✅ Swagger UI documentation
- ✅ Đọc config từ file config.json

## Cấu trúc dự án

```
pg_mcp/
├── src/
│   ├── __init__.py
│   ├── server.py          # HTTP API Server  
│   └── mcp_stdio.py       # MCP STDIO Server (cho VS Code, Claude)
├── config.json            # Cấu hình database
├── mcp-settings.json      # Cấu hình MCP cho VS Code
├── pyproject.toml         # Dependencies và metadata
├── README.md              # Tài liệu
├── MCP_STDIO_GUIDE.md     # Hướng dẫn sử dụng MCP STDIO
├── .gitignore            # Git ignore rules
├── start.bat             # Script khởi chạy HTTP server
└── uv.lock               # Lock file của uv
```

## Cài đặt và chạy

### Sử dụng uv (khuyến nghị)

1. Cài đặt uv nếu chưa có:
```bash
pip install uv
```

2. Cài đặt dependencies:
```bash
uv sync
```

3. Chạy MCP server:

**HTTP Server (cho testing thủ công):**
```bash
uv run python src/server.py
```

**STDIO Server (cho VS Code MCP, Claude Desktop):**
```bash
uv run python src/mcp_stdio.py
```

### Sử dụng pip truyền thống

1. Tạo môi trường ảo:
```bash
python -m venv .venv
```

2. Kích hoạt môi trường ảo:
```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows Command Prompt  
.venv\Scripts\activate.bat

# macOS/Linux
source .venv/bin/activate
```

3. Cài đặt dependencies:
```bash
pip install -e .
```

4. Chạy MCP server:

**HTTP Server (cho testing thủ công):**
```bash
python src/server.py
```

**STDIO Server (cho VS Code MCP, Claude Desktop):**
```bash
python src/mcp_stdio.py
```

## Sử dụng

### 🌐 HTTP API (cho testing)

Server sẽ chạy trên port 8888. Các endpoint có sẵn:

- **GET /** - Thông tin về server
- **POST /connect** - Kết nối đến PostgreSQL
- **POST /connect-default** - Kết nối với config từ config.json
- **POST /count-databases** - Đếm số lượng database
- **POST /list-databases** - Liệt kê tất cả database
- **POST /list-schemas** - Liệt kê tất cả schema
- **POST /list-tables** - Liệt kê tất cả table trong schema
- **POST /table-structure** - Xem cấu trúc của table
- **POST /table-data** - Xem dữ liệu từ table
- **POST /execute-query** - Thực thi SQL query
- **GET /health** - Health check
- **GET /docs** - Swagger UI documentation

### 🤖 MCP STDIO (cho AI assistants)

Để sử dụng với VS Code MCP extension hoặc Claude Desktop:

1. **Cấu hình VS Code**: Copy nội dung `mcp-settings.json` vào VS Code settings
2. **Chạy STDIO server**: `uv run python src/mcp_stdio.py`
3. **Trò chuyện với AI**: 
   - "Kết nối PostgreSQL"
   - "Có bao nhiêu database?"
   - "Liệt kê tất cả table"
   - "Xem cấu trúc table res_users"
   - "Cho tôi 10 user đầu tiên"

📖 **Chi tiết**: Xem `MCP_STDIO_GUIDE.md` để biết cách sử dụng đầy đủ.

## API Documentation

Mở trình duyệt và truy cập:
- http://localhost:8888 - Thông tin server
- http://localhost:8888/docs - Swagger UI để test API

## Ví dụ sử dụng

### 1. Kết nối đến PostgreSQL

```bash
curl -X POST "http://localhost:8888/connect" \
     -H "Content-Type: application/json" \
     -d '{
       "host": "localhost",
       "port": 5432,
       "user": "postgres",
       "password": "your_password",
       "database": "postgres"
     }'
```

### 2. Kết nối với config mặc định

```bash
curl -X POST "http://localhost:8888/connect-default" \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 3. Đếm số lượng database

```bash
curl -X POST "http://localhost:8888/count-databases" \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 4. Liệt kê tất cả database

```bash
curl -X POST "http://localhost:8888/list-databases" \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 5. Liệt kê schema

```bash
curl -X POST "http://localhost:8888/list-schemas" \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 6. Liệt kê table trong schema

```bash
curl -X POST "http://localhost:8888/list-tables" \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 7. Xem cấu trúc table

```bash
curl -X POST "http://localhost:8888/table-structure" \
     -H "Content-Type: application/json" \
     -d '{
       "table_name": "res_users",
       "schema_name": "public"
     }'
```

### 8. Xem dữ liệu từ table

```bash
curl -X POST "http://localhost:8888/table-data" \
     -H "Content-Type: application/json" \
     -d '{
       "table_name": "res_users", 
       "schema_name": "public"
     }'
```

### 9. Thực thi SQL query

```bash
curl -X POST "http://localhost:8888/execute-query" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "SELECT id, login, active FROM res_users WHERE active = true",
       "limit": 10
     }'
```

### 10. Health check

```bash
curl -X GET "http://localhost:8888/health"
```

## Response Format

Tất cả response đều có format JSON:

```json
{
  "success": true,
  "message": "Thông báo",
  "data": "Dữ liệu tùy thuộc vào endpoint"
}
```

## Lưu ý

- Cần cài đặt và chạy PostgreSQL server trước khi sử dụng
- Đảm bảo thông tin kết nối PostgreSQL chính xác
- Server sẽ chạy ở background, sử dụng Ctrl+C để dừng