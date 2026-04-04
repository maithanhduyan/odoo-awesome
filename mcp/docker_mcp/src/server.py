#!/usr/bin/env python3
"""
Docker MCP Server - Entry Point
Chỉ sử dụng chuẩn MCP (Model Context Protocol)
"""

import sys
import asyncio


def main():
    """Main entry point cho Docker MCP Server"""
    # Chỉ hỗ trợ MCP protocol
    mode = "mcp"
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--help", "-h"]:
            print("Docker MCP Server v1.0")
            print("Usage: python server.py [mcp]")
            print("  mcp: MCP protocol mode (default)")
            return
        elif sys.argv[1] == "mcp":
            mode = "mcp"
        else:
            print(
                f"Unknown mode: {sys.argv[1]}. Only 'mcp' mode is supported.", file=sys.stderr)
            print("Use --help for more information.", file=sys.stderr)
            sys.exit(1)
      # Sử dụng MCP protocol chuẩn
    from stdio_mcp import main as mcp_main
    asyncio.run(mcp_main())


if __name__ == "__main__":
    main()
