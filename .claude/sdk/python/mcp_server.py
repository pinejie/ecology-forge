#!/usr/bin/env python3
"""
MCP Server for 泛微 e-cology OA 二次开发。

统一入口，所有泛微二开能力的 SDK 都注册为 MCP tool。
AI 在处理泛微二开需求时，从此 MCP Server 选择合适的 tool。

环境变量：
    OA_DB_HOST     - 数据库主机（默认 172.18.28.108）
    OA_DB_USER     - 数据库用户（默认 sa）
    OA_DB_PASSWORD - 数据库密码（必填）
    OA_DB_DATABASE - 数据库名（默认 ecology）

启动方式：
    OA_DB_PASSWORD=xxx python3 mcp_server.py
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
