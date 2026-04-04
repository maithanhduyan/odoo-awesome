#!/usr/bin/env python3
"""
Docker MCP Server - Standard MCP Protocol Version
Sử dụng chuẩn MCP (Model Context Protocol)
Hỗ trợ các lệnh Docker cơ bản với bảo mật và hiệu suất cải thiện.
"""

import asyncio
import json
import sys
import subprocess
import logging
import os
import re
import socket
from typing import Any, Sequence, Dict, List, Union
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

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Security: Enable Docker Content Trust
os.environ["DOCKER_CONTENT_TRUST"] = "1"

# Timeout mặc định cho các lệnh khác nhau (giây)
COMMAND_TIMEOUTS = {
    "build": 600,  # 10 phút
    "pull": 300,   # 5 phút
    "push": 300,   # 5 phút
    "compose_up": 300,  # 5 phút
    "default": 60  # 1 phút
}

# Validation cho prune types
VALID_PRUNE_TYPES = ["system", "container", "image", "volume", "network"]

# Server instance
server = Server("docker-mcp")


def sanitize_container_name(name: str) -> bool:
    """Kiểm tra tên container/image có hợp lệ không (hỗ trợ cả tag)"""
    if not name or len(name) > 200:
        return False
    # Cho phép alphanumeric, dấu gạch ngang, underscore, dấu chấm, dấu hai chấm và slash
    return bool(re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_./-]*(?::[a-zA-Z0-9._-]+)?$', name))


def validate_safe_build_path(path: str) -> bool:
    """Kiểm tra build path có an toàn không"""
    abs_path = os.path.abspath(path)
    current_dir = os.getcwd()

    # Resolve symbolic links để tránh symlink attacks
    real_path = os.path.realpath(abs_path)
    real_current = os.path.realpath(current_dir)

    return real_path.startswith(real_current) and '..' not in path


def validate_file_exists(filepath: str) -> bool:
    """Kiểm tra file có tồn tại không"""
    return os.path.isfile(filepath)


def is_port_available(port: int, host: str = "localhost") -> bool:
    """Kiểm tra port có đang được sử dụng không"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0  # Port available if connection fails
    except Exception:
        return False


def validate_port_number(port: int) -> bool:
    """Kiểm tra port number có hợp lệ không"""
    return 1 <= port <= 65535


async def run_docker_command(cmd_args: List[str], timeout: int = None) -> Dict[str, Any]:
    """Thực thi lệnh docker với xử lý lỗi cải thiện"""
    if timeout is None:
        timeout = COMMAND_TIMEOUTS["default"]

    # Giới hạn kích thước output
    MAX_OUTPUT_SIZE = 10 * 1024 * 1024  # 10MB

    try:
        logger.info(f"Executing command: {' '.join(cmd_args)}")

        # Sử dụng asyncio.create_subprocess_exec để chạy async
        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            # Sử dụng wait_for để xử lý timeout
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            # Hủy tiến trình nếu timeout
            process.terminate()
            await asyncio.sleep(1)  # Chờ 1s để process phản hồi
            if process.returncode is None:
                process.kill()
            await process.wait()
            logger.error(
                f"Command timeout after {timeout}s: {' '.join(cmd_args)}")
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timeout after {timeout} seconds"
            }

        stdout_str = stdout.decode('utf-8', errors='replace')
        stderr_str = stderr.decode('utf-8', errors='replace')

        # Giới hạn kích thước output
        if len(stdout_str) > MAX_OUTPUT_SIZE:
            stdout_str = stdout_str[:MAX_OUTPUT_SIZE] + \
                "\n...[OUTPUT TRUNCATED]"
        if len(stderr_str) > MAX_OUTPUT_SIZE:
            stderr_str = stderr_str[:MAX_OUTPUT_SIZE] + \
                "\n...[ERROR TRUNCATED]"

        return {
            "returncode": process.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str
        }
    except Exception as e:
        logger.error(f"Unexpected error executing command: {e}")
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Unexpected error: {str(e)}"
        }


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available Docker tools"""
    return [
        Tool(
            name="docker_list",
            description="Liệt kê tất cả Docker containers",
            inputSchema={
                "type": "object",
                "properties": {
                    "all": {"type": "boolean", "description": "Hiển thị tất cả containers (bao gồm stopped)", "default": True}
                },
            },
        ),
        Tool(
            name="docker_start",
            description="Khởi động Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_stop",
            description="Dừng Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_restart",
            description="Khởi động lại Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_logs",
            description="Xem logs của Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"},
                    "tail": {"type": "integer", "description": "Số dòng log cuối cần hiển thị", "default": 100}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_status",
            description="Kiểm tra thông tin chi tiết container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_exec",
            description="Thực thi lệnh trong container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"},
                    "command": {"type": "string", "description": "Lệnh cần thực thi", "default": "bash"},
                    "interactive": {"type": "boolean", "description": "Chế độ interactive", "default": True}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_remove",
            description="Xóa Docker container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"},
                    "force": {"type": "boolean", "description": "Buộc xóa (ngay cả khi đang chạy)", "default": False}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_stats",
            description="Thống kê tài nguyên containers",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên container cụ thể (để trống = tất cả)"},
                    "no_stream": {"type": "boolean", "description": "Không stream continuous", "default": True}
                },
            },
        ),
        Tool(
            name="docker_images",
            description="Liệt kê tất cả Docker images",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="docker_build",
            description="Build Docker image từ Dockerfile",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Đường dẫn build context", "default": "."},
                    "tag": {"type": "string", "description": "Tag cho image"},
                    "dockerfile": {"type": "string", "description": "Tên file Dockerfile", "default": "Dockerfile"}
                },
            },
        ),
        Tool(
            name="docker_pull",
            description="Pull Docker image từ registry",
            inputSchema={
                "type": "object",
                "properties": {
                    "image": {"type": "string", "description": "Tên image cần pull"}
                },
                "required": ["image"]
            },
        ),
        Tool(
            name="docker_volumes",
            description="Liệt kê Docker volumes",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="docker_networks",
            description="Liệt kê Docker networks",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="compose_up",
            description="Khởi động services từ Docker Compose file",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Đường dẫn compose file", "default": "compose.yml"},
                    "detach": {"type": "boolean", "description": "Chạy ở background", "default": True}
                },
            },
        ),
        Tool(
            name="compose_down",
            description="Dừng và xóa services từ Docker Compose",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Đường dẫn compose file", "default": "compose.yml"}
                },
            },
        ),        Tool(
            name="compose_logs",
            description="Xem logs từ Docker Compose services",
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Đường dẫn compose file", "default": "compose.yml"},
                    "service": {"type": "string", "description": "Service cụ thể"},
                    "tail": {"type": "integer", "description": "Số dòng log cuối", "default": 100}
                },
            },
        ),
        Tool(
            name="docker_ports",
            description="Xem port mapping của container",
            inputSchema={
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Tên hoặc ID của container"}
                },
                "required": ["container"]
            },
        ),
        Tool(
            name="docker_port_check",
            description="Kiểm tra port có đang được sử dụng không",
            inputSchema={
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "Port number cần kiểm tra"},
                    "host": {"type": "string", "description": "Host để kiểm tra", "default": "localhost"}
                },
                "required": ["port"]
            },
        ),
        Tool(
            name="docker_port_scan",
            description="Scan ports available trong khoảng cho trước",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_port": {"type": "integer", "description": "Port bắt đầu", "default": 8000},
                    "end_port": {"type": "integer", "description": "Port kết thúc", "default": 8010},
                    "host": {"type": "string", "description": "Host để scan", "default": "localhost"}
                },
            },
        ),
        Tool(
            name="docker_prune",
            description="Dọn dẹp tài nguyên Docker không sử dụng",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "Loại prune", "enum": VALID_PRUNE_TYPES, "default": "system"},
                    "force": {"type": "boolean", "description": "Không hỏi xác nhận", "default": True}
                },
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool execution requests"""
    if arguments is None:
        arguments = {}

    try:
        if name == "docker_list":
            all_containers = arguments.get("all", True)
            cmd_args = ["docker", "ps"]
            if all_containers:
                cmd_args.append("-a")

            result = await run_docker_command(cmd_args)
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"🐳 **Docker Containers:**\n```\n{result['stdout']}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi: {result['stderr']}")]

        elif name == "docker_start":
            container = arguments.get("container")
            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            result = await run_docker_command(["docker", "start", container])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Container '{container}' đã được khởi động")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi khởi động container: {result['stderr']}")]

        elif name == "docker_stop":
            container = arguments.get("container")
            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            result = await run_docker_command(["docker", "stop", container])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Container '{container}' đã được dừng")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi dừng container: {result['stderr']}")]

        elif name == "docker_restart":
            container = arguments.get("container")
            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            result = await run_docker_command(["docker", "restart", container])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Container '{container}' đã được khởi động lại")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi khởi động lại container: {result['stderr']}")]

        elif name == "docker_logs":
            container = arguments.get("container")
            tail = arguments.get("tail", 100)

            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            if tail < 0 or tail > 10000:
                return [TextContent(type="text", text="❌ Tail phải trong khoảng 0-10000")]

            result = await run_docker_command(["docker", "logs", "--tail", str(tail), container])
            if result["returncode"] == 0:
                logs = result["stdout"] if result["stdout"] else "(Không có logs)"
                return [TextContent(type="text", text=f"📋 **Logs của container '{container}' ({tail} dòng cuối):**\n```\n{logs}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy logs: {result['stderr']}")]

        elif name == "docker_status":
            container = arguments.get("container")
            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            result = await run_docker_command(["docker", "inspect", container])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"🔍 **Chi tiết container '{container}':**\n```json\n{result['stdout']}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy thông tin container: {result['stderr']}")]

        elif name == "docker_exec":
            container = arguments.get("container")
            command = arguments.get("command", "bash")
            interactive = arguments.get("interactive", True)

            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            # Enhanced security check for command
            safe_commands = ["bash", "sh", "ls", "pwd", "whoami", "ps", "top"]
            allowed_with_params = ["cat", "tail",
                                   "head", "grep", "find", "du", "df"]

            cmd_parts = command.split()
            if not cmd_parts:
                return [TextContent(type="text", text="❌ Lệnh trống không được phép")]

            base_cmd = cmd_parts[0]
            if base_cmd not in safe_commands and base_cmd not in allowed_with_params:
                return [TextContent(type="text", text=f"❌ Lệnh '{base_cmd}' không được phép vì lý do bảo mật")]

            # Enhanced dangerous patterns check
            dangerous_patterns = [
                'rm', 'sudo', 'su', 'chmod', 'chown', 'mv', 'cp', '>', '>>', '|', '&', ';', '`', '$',
                'wget', 'curl', 'nc', 'netcat', 'ssh', 'scp', 'chroot', 'dd', 'mkfs',
                'passwd', 'useradd', 'usermod', 'groupadd', 'visudo', 'crontab'
            ]

            for pattern in dangerous_patterns:
                if pattern in command:
                    return [TextContent(type="text", text=f"❌ Phát hiện pattern nguy hiểm '{pattern}' trong lệnh")]

            # Enhanced regex checks for dangerous patterns
            dangerous_regex = [
                r'\brm\s+-[rf]',  # rm -rf
                r'\bchmod\s+[0-7]{3,4}\s+',  # chmod với quyền nguy hiểm
                r'\bchown\s+[0-9]+:[0-9]+',  # chown với UID/GID
                # di chuyển/sao chép vào thư mục hệ thống            ]
                r'\b(mv|cp)\s+.*\s+/',
            ]
            for regex_pattern in dangerous_regex:
                if re.search(regex_pattern, command):
                    return [TextContent(type="text", text=f"❌ Phát hiện pattern regex nguy hiểm trong lệnh")]

            cmd_args = ["docker", "exec"]
            if interactive:
                cmd_args.append("-i")
            cmd_args.append(container)
            cmd_args.extend(cmd_parts)

            result = await run_docker_command(cmd_args)
            if result["returncode"] == 0:
                output = result["stdout"] if result["stdout"] else "(Không có output)"
                return [TextContent(type="text", text=f"⚡ **Exec trong '{container}':**\n```\n{output}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi exec: {result['stderr']}")]

        elif name == "docker_remove":
            container = arguments.get("container")
            force = arguments.get("force", False)

            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            cmd_args = ["docker", "rm"]
            if force:
                cmd_args.append("-f")
            cmd_args.append(container)

            result = await run_docker_command(cmd_args)
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Container '{container}' đã được xóa")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi xóa container: {result['stderr']}")]

        elif name == "docker_stats":
            container = arguments.get("container", "")
            no_stream = arguments.get("no_stream", True)

            if container and not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            cmd_args = ["docker", "stats"]
            if no_stream:
                cmd_args.append("--no-stream")
            if container:
                cmd_args.append(container)

            result = await run_docker_command(cmd_args)
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"📊 **Docker Stats:**\n```\n{result['stdout']}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy stats: {result['stderr']}")]

        elif name == "docker_images":
            result = await run_docker_command(["docker", "images"])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"🖼️ **Docker Images:**\n```\n{result['stdout']}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy danh sách images: {result['stderr']}")]

        elif name == "docker_build":
            path = arguments.get("path", ".")
            tag = arguments.get("tag")
            dockerfile = arguments.get("dockerfile", "Dockerfile")

            if not validate_safe_build_path(path):
                return [TextContent(type="text", text="❌ Đường dẫn build không an toàn - phải nằm trong workspace hiện tại")]

            if not os.path.exists(path):
                return [TextContent(type="text", text=f"❌ Đường dẫn build không tồn tại: {path}")]

            dockerfile_path = os.path.join(path, dockerfile)
            if not validate_file_exists(dockerfile_path):
                return [TextContent(type="text", text=f"❌ Dockerfile không tồn tại: {dockerfile_path}")]
            cmd_args = ["docker", "build"]
            cmd_args.extend(["--security-opt", "no-new-privileges"])
            cmd_args.extend(["-f", dockerfile])

            if tag:
                if not sanitize_container_name(tag):
                    return [TextContent(type="text", text="❌ Tag không hợp lệ")]
                cmd_args.extend(["-t", tag])

            cmd_args.append(path)

            result = await run_docker_command(cmd_args, timeout=COMMAND_TIMEOUTS["build"])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Build thành công{f' với tag: {tag}' if tag else ''}")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi build: {result['stderr']}")]

        elif name == "docker_pull":
            image = arguments.get("image")
            if not sanitize_container_name(image):
                return [TextContent(type="text", text="❌ Tên image không hợp lệ")]

            result = await run_docker_command(["docker", "pull", image], timeout=COMMAND_TIMEOUTS["pull"])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Pull thành công image: {image}")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi pull image: {result['stderr']}")]

        elif name == "docker_volumes":
            result = await run_docker_command(["docker", "volume", "ls"])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"💾 **Docker Volumes:**\n```\n{result['stdout']}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy danh sách volumes: {result['stderr']}")]

        elif name == "docker_networks":
            result = await run_docker_command(["docker", "network", "ls"])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"🌐 **Docker Networks:**\n```\n{result['stdout']}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy danh sách networks: {result['stderr']}")]

        elif name == "compose_up":
            file = arguments.get("file", "compose.yml")
            detach = arguments.get("detach", True)

            if not validate_file_exists(file):
                return [TextContent(type="text", text=f"❌ Compose file không tồn tại: {file}")]

            cmd_args = ["docker", "compose", "-f", file, "up"]
            if detach:
                cmd_args.append("-d")

            result = await run_docker_command(cmd_args, timeout=COMMAND_TIMEOUTS["compose_up"])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Compose up thành công từ file: {file}")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi compose up: {result['stderr']}")]

        elif name == "compose_down":
            file = arguments.get("file", "compose.yml")

            if not validate_file_exists(file):
                return [TextContent(type="text", text=f"❌ Compose file không tồn tại: {file}")]

            result = await run_docker_command(["docker", "compose", "-f", file, "down"])
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Compose down thành công từ file: {file}")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi compose down: {result['stderr']}")]

        elif name == "compose_logs":
            file = arguments.get("file", "compose.yml")
            service = arguments.get("service", "")
            tail = arguments.get("tail", 100)

            if not validate_file_exists(file):
                return [TextContent(type="text", text=f"❌ Compose file không tồn tại: {file}")]

            if service and not sanitize_container_name(service):
                return [TextContent(type="text", text="❌ Tên service không hợp lệ")]

            if tail < 0 or tail > 10000:
                return [TextContent(type="text", text="❌ Tail phải trong khoảng 0-10000")]

            cmd_args = ["docker", "compose", "-f",
                        file, "logs", "--tail", str(tail)]
            if service:
                cmd_args.append(service)

            result = await run_docker_command(cmd_args)
            if result["returncode"] == 0:
                logs = result["stdout"] if result["stdout"] else "(Không có logs)"
                target = f"service '{service}'" if service else "tất cả services"
                return [TextContent(type="text", text=f"📋 **Compose logs của {target}:**\n```\n{logs}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy compose logs: {result['stderr']}")]

        elif name == "docker_ports":
            container = arguments.get("container")
            if not sanitize_container_name(container):
                return [TextContent(type="text", text="❌ Tên container không hợp lệ")]

            result = await run_docker_command(["docker", "port", container])
            if result["returncode"] == 0:
                ports_info = result["stdout"] if result["stdout"] else "(Không có port mapping)"
                return [TextContent(type="text", text=f"🌐 **Port mapping của container '{container}':**\n```\n{ports_info}\n```")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi lấy port mapping: {result['stderr']}")]

        elif name == "docker_port_check":
            port = arguments.get("port")
            host = arguments.get("host", "localhost")

            if not validate_port_number(port):
                return [TextContent(type="text", text="❌ Port number không hợp lệ (phải từ 1-65535)")]

            try:
                is_available = is_port_available(port, host)
                status = "🟢 Available" if is_available else "🔴 In use"
                return [TextContent(type="text", text=f"🔍 **Port {port} trên {host}:** {status}")]
            except Exception as e:
                return [TextContent(type="text", text=f"❌ Lỗi kiểm tra port: {str(e)}")]

        elif name == "docker_port_scan":
            start_port = arguments.get("start_port", 8000)
            end_port = arguments.get("end_port", 8010)
            host = arguments.get("host", "localhost")

            if not validate_port_number(start_port) or not validate_port_number(end_port):
                return [TextContent(type="text", text="❌ Port numbers không hợp lệ (phải từ 1-65535)")]

            if start_port > end_port:
                return [TextContent(type="text", text="❌ Start port phải nhỏ hơn hoặc bằng end port")]

            if end_port - start_port > 100:
                return [TextContent(type="text", text="❌ Khoảng scan không được vượt quá 100 ports")]

            try:
                available_ports = []
                used_ports = []

                for port in range(start_port, end_port + 1):
                    if is_port_available(port, host):
                        available_ports.append(port)
                    else:
                        used_ports.append(port)

                result_text = f"🔍 **Port scan từ {start_port} đến {end_port} trên {host}:**\n\n"
                result_text += f"🟢 **Available ports ({len(available_ports)}):** {', '.join(map(str, available_ports)) if available_ports else 'Không có'}\n\n"
                result_text += f"🔴 **Used ports ({len(used_ports)}):** {', '.join(map(str, used_ports)) if used_ports else 'Không có'}"

                return [TextContent(type="text", text=result_text)]
            except Exception as e:
                return [TextContent(type="text", text=f"❌ Lỗi scan ports: {str(e)}")]

        elif name == "docker_prune":
            prune_type = arguments.get("type", "system")
            force = arguments.get("force", True)

            if prune_type not in VALID_PRUNE_TYPES:
                return [TextContent(type="text", text=f"❌ Loại prune không hợp lệ. Phải là một trong: {VALID_PRUNE_TYPES}")]

            cmd_args = ["docker"]
            if prune_type == "system":
                cmd_args.extend(["system", "prune"])
            else:
                cmd_args.extend([prune_type, "prune"])

            if force:
                cmd_args.append("-f")

            result = await run_docker_command(cmd_args)
            if result["returncode"] == 0:
                return [TextContent(type="text", text=f"✅ Prune {prune_type} thành công")]
            else:
                return [TextContent(type="text", text=f"❌ Lỗi prune: {result['stderr']}")]

        else:
            return [TextContent(type="text", text=f"❌ Tool '{name}' không tồn tại")]

    except Exception as e:
        logger.error(f"Error in handle_call_tool: {e}")
        return [TextContent(type="text", text=f"❌ Lỗi: {str(e)}")]


async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="docker-mcp",
                server_version="2.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
