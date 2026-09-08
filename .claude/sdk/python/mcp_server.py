#!/usr/bin/env python3
"""
MCP Server for 泛微 e-cology OA 二次开发。

统一入口，所有泛微二开能力的 SDK 都注册为 MCP tool。
AI 在处理泛微二开需求时，从此 MCP Server 选择合适的 tool。

数据库配置从 .claude/sdk/db-config.md 读取。

启动方式：
    python3 mcp_server.py
"""

from mcp.server.fastmcp import FastMCP
from mcp_register import auto_register

# ============================================================
#  服务器初始化
# ============================================================

mcp = FastMCP("weaver_oa_mcp")

# 自动注册所有 SDK 模块中带 @expose 标记的方法
auto_register(mcp)

# ============================================================
#  入口
# ============================================================

if __name__ == "__main__":
    mcp.run()
