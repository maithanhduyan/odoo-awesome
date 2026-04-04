#!/usr/bin/env python3
"""
PostgreSQL MCP Server - STDIO Version
Để sử dụng với VS Code MCP extension và các MCP clients khác
"""

import asyncio
import json
import sys
import psycopg2
from typing import Any, Sequence
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
import os

# Load config from config.json
def load_config():
    """Load database configuration from config.json"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config.get("database", {})
    except Exception as e:
        return {}

# Global variables
postgres_connection = None
default_config = load_config()

# Server instance
server = Server("postgres-mcp")

async def connect_postgres(host="localhost", port=5432, user="postgres", password="", database="postgres"):
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
        return True
    except Exception as e:
        return False

async def safe_execute_query(query: str, params=None):
    """Thực thi query an toàn"""
    global postgres_connection
    if not postgres_connection:
        return {"success": False, "message": "Chưa kết nối đến PostgreSQL"}
    
    try:
        cursor = postgres_connection.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        # Kiểm tra xem có kết quả không
        if cursor.description:
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()
            return {"success": True, "data": rows, "columns": columns}
        else:
            cursor.close()
            return {"success": True, "message": "Query thực thi thành công"}
    except Exception as e:
        return {"success": False, "message": str(e)}

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        Tool(
            name="connect_postgres",
            description="Kết nối đến PostgreSQL server",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {"type": "string", "description": "Địa chỉ server", "default": "localhost"},
                    "port": {"type": "integer", "description": "Cổng kết nối", "default": 5432},
                    "user": {"type": "string", "description": "Tên người dùng", "default": "postgres"},
                    "password": {"type": "string", "description": "Mật khẩu"},
                    "database": {"type": "string", "description": "Tên database", "default": "postgres"}
                },
                "required": ["password"]
            },
        ),
        Tool(
            name="connect_default",
            description="Kết nối PostgreSQL với config mặc định từ config.json",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="count_databases",
            description="Đếm số lượng database trong PostgreSQL",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_databases",
            description="Liệt kê tất cả database",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_schemas",
            description="Liệt kê tất cả schema trong database hiện tại",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="list_tables",
            description="Liệt kê tất cả table trong schema",
            inputSchema={
                "type": "object",
                "properties": {
                    "schema_name": {"type": "string", "description": "Tên schema", "default": "public"}
                },
            },
        ),
        Tool(
            name="table_structure",
            description="Lấy cấu trúc chi tiết của table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Tên table"},
                    "schema_name": {"type": "string", "description": "Tên schema", "default": "public"}
                },
                "required": ["table_name"]
            },
        ),
        Tool(
            name="table_data",
            description="Lấy dữ liệu từ table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "Tên table"},
                    "schema_name": {"type": "string", "description": "Tên schema", "default": "public"},
                    "limit": {"type": "integer", "description": "Số lượng record tối đa", "default": 10}
                },
                "required": ["table_name"]
            },
        ),
        Tool(
            name="execute_query",
            description="Thực thi SQL query (chỉ SELECT)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SQL query để thực thi"},
                    "limit": {"type": "integer", "description": "Số lượng record tối đa", "default": 100}
                },
                "required": ["query"]
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | ImageContent | EmbeddedResource]:
    """
    Handle tool execution requests.
    """
    if arguments is None:
        arguments = {}

    try:
        if name == "connect_postgres":
            result = await connect_postgres(
                host=arguments.get("host", "localhost"),
                port=arguments.get("port", 5432),
                user=arguments.get("user", "postgres"),
                password=arguments.get("password", ""),
                database=arguments.get("database", "postgres")
            )
            message = "✅ Kết nối thành công!" if result else "❌ Kết nối thất bại!"
            return [TextContent(type="text", text=message)]

        elif name == "connect_default":
            if not default_config:
                return [TextContent(type="text", text="❌ Không tìm thấy config.json")]
            
            result = await connect_postgres(
                host=default_config.get("host", "localhost"),
                port=default_config.get("port", 5432),
                user=default_config.get("user", "postgres"),
                password=default_config.get("password", ""),
                database=default_config.get("database", "postgres")
            )
            message = "✅ Kết nối thành công với config mặc định!" if result else "❌ Kết nối thất bại!"
            return [TextContent(type="text", text=message)]

        elif name == "count_databases":
            result = await safe_execute_query(
                "SELECT COUNT(*) FROM pg_database WHERE datistemplate = false;"
            )
            if result["success"]:
                count = result["data"][0][0]
                return [TextContent(type="text", text=f"📊 Số lượng database: {count}")]
            else:
                return [TextContent(type="text", text=f"❌ {result['message']}")]

        elif name == "list_databases":
            result = await safe_execute_query(
                "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname;"
            )
            if result["success"]:
                databases = [row[0] for row in result["data"]]
                db_list = "\n".join([f"• {db}" for db in databases])
                return [TextContent(type="text", text=f"📋 Danh sách database:\n{db_list}")]
            else:
                return [TextContent(type="text", text=f"❌ {result['message']}")]

        elif name == "list_schemas":
            result = await safe_execute_query("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ORDER BY schema_name;
            """)
            if result["success"]:
                schemas = [row[0] for row in result["data"]]
                schema_list = "\n".join([f"• {schema}" for schema in schemas])
                return [TextContent(type="text", text=f"🗂️ Danh sách schema:\n{schema_list}")]
            else:
                return [TextContent(type="text", text=f"❌ {result['message']}")]

        elif name == "list_tables":
            schema_name = arguments.get("schema_name", "public")
            result = await safe_execute_query("""
                SELECT table_name, table_type
                FROM information_schema.tables 
                WHERE table_schema = %s
                ORDER BY table_name;
            """, (schema_name,))
            if result["success"]:
                tables = [f"• {row[0]} ({row[1]})" for row in result["data"]]
                table_list = "\n".join(tables)
                return [TextContent(type="text", text=f"📋 Tables trong schema '{schema_name}':\n{table_list}")]
            else:
                return [TextContent(type="text", text=f"❌ {result['message']}")]

        elif name == "table_structure":
            table_name = arguments.get("table_name")
            schema_name = arguments.get("schema_name", "public")
            
            # Lấy thông tin cột
            result = await safe_execute_query("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length
                FROM information_schema.columns 
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position;
            """, (schema_name, table_name))
            
            if result["success"]:
                columns_info = []
                for row in result["data"]:
                    col_name, data_type, nullable, default, max_len = row
                    info = f"• {col_name}: {data_type}"
                    if max_len:
                        info += f"({max_len})"
                    if nullable == "NO":
                        info += " NOT NULL"
                    if default:
                        info += f" DEFAULT {default}"
                    columns_info.append(info)
                
                structure = "\n".join(columns_info)
                return [TextContent(type="text", text=f"🏗️ Cấu trúc table '{table_name}':\n{structure}")]
            else:
                return [TextContent(type="text", text=f"❌ {result['message']}")]

        elif name == "table_data":
            table_name = arguments.get("table_name")
            schema_name = arguments.get("schema_name", "public")
            limit = arguments.get("limit", 10)
            
            result = await safe_execute_query(
                f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT %s;',
                (limit,)
            )
            
            if result["success"]:
                if not result["data"]:
                    return [TextContent(type="text", text=f"📊 Table '{table_name}' không có dữ liệu")]
                
                # Format dữ liệu
                columns = result["columns"]
                data_text = f"📊 Dữ liệu từ table '{table_name}' (tối đa {limit} records):\n\n"
                data_text += "Columns: " + " | ".join(columns) + "\n"
                data_text += "-" * 80 + "\n"
                
                for row in result["data"][:5]:  # Chỉ hiển thị 5 dòng đầu
                    row_text = " | ".join([str(val)[:20] if val is not None else "NULL" for val in row])
                    data_text += row_text + "\n"
                
                if len(result["data"]) > 5:
                    data_text += f"\n... và {len(result['data']) - 5} dòng khác"
                
                return [TextContent(type="text", text=data_text)]
            else:
                return [TextContent(type="text", text=f"❌ {result['message']}")]

        elif name == "execute_query":
            query = arguments.get("query", "")
            limit = arguments.get("limit", 100)
            
            # Kiểm tra query chỉ là SELECT
            if not query.lower().strip().startswith('select'):
                return [TextContent(type="text", text="❌ Chỉ cho phép SELECT query để đảm bảo an toàn")]
            
            # Thêm LIMIT nếu chưa có
            if 'limit' not in query.lower():
                query = f"{query.rstrip(';')} LIMIT {limit};"
            
            result = await safe_execute_query(query)
            
            if result["success"]:
                if not result["data"]:
                    return [TextContent(type="text", text="📊 Query không trả về dữ liệu")]
                
                columns = result["columns"]
                data_text = f"📊 Kết quả query:\n\n"
                data_text += "Columns: " + " | ".join(columns) + "\n"
                data_text += "-" * 80 + "\n"
                
                for row in result["data"][:10]:  # Chỉ hiển thị 10 dòng đầu
                    row_text = " | ".join([str(val)[:20] if val is not None else "NULL" for val in row])
                    data_text += row_text + "\n"
                
                if len(result["data"]) > 10:
                    data_text += f"\n... và {len(result['data']) - 10} dòng khác"
                
                return [TextContent(type="text", text=data_text)]
            else:
                return [TextContent(type="text", text=f"❌ {result['message']}")]

        else:
            return [TextContent(type="text", text=f"❌ Tool '{name}' không tồn tại")]

    except Exception as e:
        return [TextContent(type="text", text=f"❌ Lỗi: {str(e)}")]

async def main():
    # Run the server using stdio
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="postgres-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
