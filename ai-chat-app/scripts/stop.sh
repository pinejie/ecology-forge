#!/bin/bash
echo "停止 AI Chat App..."
pkill -f "uvicorn app.main:app" 2>/dev/null && echo "后端已停止" || echo "后端未运行"
pkill -f "next dev" 2>/dev/null && echo "前端已停止" || echo "前端未运行"
