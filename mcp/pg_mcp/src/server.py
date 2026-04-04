import asyncio
import psycopg2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn
import json
import os

# Pydantic models cho requests
class ConnectRequest(BaseModel):
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str
    database: str = "postgres"

class EmptyRequest(BaseModel):
    pass

class QueryRequest(BaseModel):
    query: str
    limit: Optional[int] = 100

class TableInfoRequest(BaseModel):
    table_name: str
    schema_name: str = "public"

class DatabaseInfoRequest(BaseModel):
    database_name: str

# Global connection variable
postgres_connection = None

# Load config from config.json
def load_config():
    """Load database configuration from config.json"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config.get("database", {})
    except Exception as e:
        print(f"Lỗi đọc config.json: {e}")
        return {}

# Load default config
default_config = load_config()

# FastAPI app
app = FastAPI(title="PostgreSQL MCP Server", version="1.0.0")

async def connect_postgres(host: str, port: int, user: str, password: str, database: str):
    """Kết nối đến PostgreSQL server"""
    global postgres_connection
    try:
        postgres_connection = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        return {"success": True, "message": "Kết nối thành công!"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi kết nối PostgreSQL: {e}"}

async def count_databases():
    """Đếm số lượng database trong PostgreSQL"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM pg_database WHERE datistemplate = false;")
        count = cursor.fetchone()[0]
        cursor.close()
        return {"success": True, "count": count, "message": f"Số lượng database trong PostgreSQL: {count}"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi truy vấn: {e}"}

async def list_databases():
    """Liệt kê tất cả database"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;")
        databases = cursor.fetchall()
        cursor.close()
        
        db_list = [db[0] for db in databases]
        return {"success": True, "databases": db_list, "message": f"Danh sách database: {', '.join(db_list)}"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi truy vấn: {e}"}

async def list_schemas(database_name: str = None):
    """Liệt kê tất cả schema trong database hiện tại"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        cursor.execute("""
            SELECT schema_name 
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY schema_name;
        """)
        schemas = cursor.fetchall()
        cursor.close()
        
        schema_list = [schema[0] for schema in schemas]
        return {"success": True, "schemas": schema_list, "message": f"Danh sách schema: {', '.join(schema_list)}"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi truy vấn: {e}"}

async def list_tables(schema_name: str = "public"):
    """Liệt kê tất cả table trong schema"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        cursor.execute("""
            SELECT table_name, table_type
            FROM information_schema.tables 
            WHERE table_schema = %s
            ORDER BY table_name;
        """, (schema_name,))
        tables = cursor.fetchall()
        cursor.close()
        
        table_list = [{"name": table[0], "type": table[1]} for table in tables]
        return {"success": True, "tables": table_list, "schema": schema_name, "count": len(table_list)}
    except Exception as e:
        return {"success": False, "message": f"Lỗi truy vấy: {e}"}

async def get_table_structure(table_name: str, schema_name: str = "public"):
    """Lấy cấu trúc của table"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns 
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """, (schema_name, table_name))
        columns = cursor.fetchall()
        
        # Lấy thông tin về khóa chính
        cursor.execute("""
            SELECT column_name
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.table_constraints tc 
                ON kcu.constraint_name = tc.constraint_name
            WHERE tc.table_schema = %s 
                AND tc.table_name = %s 
                AND tc.constraint_type = 'PRIMARY KEY';
        """, (schema_name, table_name))
        primary_keys = [row[0] for row in cursor.fetchall()]
        
        # Lấy thông tin về foreign keys
        cursor.execute("""
            SELECT 
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.key_column_usage kcu
            JOIN information_schema.table_constraints tc 
                ON kcu.constraint_name = tc.constraint_name
            JOIN information_schema.constraint_column_usage ccu 
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.table_schema = %s 
                AND tc.table_name = %s 
                AND tc.constraint_type = 'FOREIGN KEY';
        """, (schema_name, table_name))
        foreign_keys = [{"column": row[0], "references_table": row[1], "references_column": row[2]} 
                       for row in cursor.fetchall()]
        
        cursor.close()
        
        columns_info = []
        for col in columns:
            col_info = {
                "name": col[0],
                "type": col[1],
                "nullable": col[2] == "YES",
                "default": col[3],
                "is_primary_key": col[0] in primary_keys
            }
            if col[4]:  # character_maximum_length
                col_info["max_length"] = col[4]
            if col[5]:  # numeric_precision
                col_info["precision"] = col[5]
            if col[6]:  # numeric_scale
                col_info["scale"] = col[6]
            columns_info.append(col_info)
        
        return {
            "success": True, 
            "table_name": table_name,
            "schema_name": schema_name,
            "columns": columns_info,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys,
            "column_count": len(columns_info)
        }
    except Exception as e:
        return {"success": False, "message": f"Lỗi truy vấn: {e}"}

async def get_table_data(table_name: str, schema_name: str = "public", limit: int = 100):
    """Lấy dữ liệu từ table"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        
        # Lấy số lượng record
        cursor.execute(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}";')
        total_count = cursor.fetchone()[0]
        
        # Lấy dữ liệu với limit
        cursor.execute(f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT %s;', (limit,))
        rows = cursor.fetchall()
        
        # Lấy tên cột
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns 
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """, (schema_name, table_name))
        column_names = [col[0] for col in cursor.fetchall()]
        
        cursor.close()
        
        # Chuyển đổi dữ liệu thành list of dict
        data = []
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                # Chuyển đổi các kiểu dữ liệu không serialize được
                if hasattr(value, 'isoformat'):  # datetime objects
                    row_dict[column_names[i]] = value.isoformat()
                elif isinstance(value, (bytes, bytearray)):
                    row_dict[column_names[i]] = str(value)
                else:
                    row_dict[column_names[i]] = value
            data.append(row_dict)
        
        return {
            "success": True,
            "table_name": table_name,
            "schema_name": schema_name,
            "columns": column_names,
            "data": data,
            "total_count": total_count,
            "returned_count": len(data),
            "limit": limit
        }
    except Exception as e:
        return {"success": False, "message": f"Lỗi truy vấn: {e}"}

async def execute_query(query: str, limit: int = 100):
    """Thực thi query SQL tùy chỉnh"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        
        # Kiểm tra query có phải là SELECT không (an toàn)
        query_lower = query.lower().strip()
        if not query_lower.startswith('select'):
            return {"success": False, "message": "Chỉ cho phép thực thi SELECT query để đảm bảo an toàn"}
        
        # Thêm LIMIT nếu chưa có
        if 'limit' not in query_lower:
            query = f"{query.rstrip(';')} LIMIT {limit};"
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Lấy tên cột từ cursor description
        column_names = [desc[0] for desc in cursor.description] if cursor.description else []
        
        cursor.close()
        
        # Chuyển đổi dữ liệu
        data = []
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                if hasattr(value, 'isoformat'):
                    row_dict[column_names[i]] = value.isoformat()
                elif isinstance(value, (bytes, bytearray)):
                    row_dict[column_names[i]] = str(value)
                else:
                    row_dict[column_names[i]] = value
            data.append(row_dict)
        
        return {
            "success": True,
            "query": query,
            "columns": column_names,
            "data": data,
            "count": len(data)
        }
    except Exception as e:
        return {"success": False, "message": f"Lỗi thực thi query: {e}"}

# API Routes
@app.get("/")
async def root():
    """Root endpoint với thông tin về server"""
    return {
        "name": "PostgreSQL MCP Server",
        "version": "1.0.0",
        "description": "MCP Server để kết nối và truy vấn PostgreSQL database",
        "config": {
            "host": default_config.get("host", "N/A"),
            "port": default_config.get("port", "N/A"),
            "user": default_config.get("user", "N/A"),
            "database": default_config.get("database", "N/A")
        },        "endpoints": {
            "/connect": "Kết nối đến PostgreSQL với thông tin tùy chỉnh",
            "/connect-default": "Kết nối đến PostgreSQL với config mặc định",
            "/count-databases": "Đếm số lượng database",
            "/list-databases": "Liệt kê tất cả database",
            "/list-schemas": "Liệt kê tất cả schema",
            "/list-tables": "Liệt kê tất cả table trong schema",
            "/table-structure": "Lấy cấu trúc của table",
            "/table-data": "Lấy dữ liệu từ table",
            "/execute-query": "Thực thi SQL query"
        }
    }

@app.post("/connect")
async def connect_endpoint(request: ConnectRequest):
    """Endpoint để kết nối PostgreSQL"""
    result = await connect_postgres(
        host=request.host,
        port=request.port,
        user=request.user,
        password=request.password,
        database=request.database
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/connect-default")
async def connect_default_endpoint():
    """Endpoint để kết nối PostgreSQL với config mặc định"""
    if not default_config:
        raise HTTPException(status_code=400, detail="Không tìm thấy config.json hoặc config không hợp lệ")
    
    result = await connect_postgres(
        host=default_config.get("host", "localhost"),
        port=default_config.get("port", 5432),
        user=default_config.get("user", "postgres"),
        password=default_config.get("password", ""),
        database=default_config.get("database", "postgres")
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/count-databases")
async def count_databases_endpoint(request: EmptyRequest = EmptyRequest()):
    """Endpoint để đếm số lượng database"""
    result = await count_databases()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/list-databases")
async def list_databases_endpoint(request: EmptyRequest = EmptyRequest()):
    """Endpoint để liệt kê database"""
    result = await list_databases()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/list-schemas")
async def list_schemas_endpoint(request: EmptyRequest = EmptyRequest()):
    """Endpoint để liệt kê schema"""
    result = await list_schemas()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/list-tables")
async def list_tables_endpoint(request: EmptyRequest = EmptyRequest()):
    """Endpoint để liệt kê table trong schema public"""
    result = await list_tables("public")
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/table-structure")
async def get_table_structure_endpoint(request: TableInfoRequest):
    """Endpoint để lấy cấu trúc table"""
    result = await get_table_structure(request.table_name, request.schema_name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/table-data")
async def get_table_data_endpoint(request: TableInfoRequest):
    """Endpoint để lấy dữ liệu từ table"""
    result = await get_table_data(request.table_name, request.schema_name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/execute-query")
async def execute_query_endpoint(request: QueryRequest):
    """Endpoint để thực thi SQL query"""
    result = await execute_query(request.query, request.limit)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    connection_status = "connected" if postgres_connection else "disconnected"
    return {
        "status": "healthy",
        "postgres_connection": connection_status
    }

def main():
    """Hàm main để chạy HTTP server"""
    print("Đang khởi động PostgreSQL MCP Server trên port 8888...")
    print("API Documentation: http://localhost:8888/docs")
    uvicorn.run(app, host="0.0.0.0", port=8888)

if __name__ == "__main__":
    main()