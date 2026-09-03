#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
echo "=== AI Chat App 启动 ==="

# Load nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Check Node
if ! node --version | grep -q "v2[0-9]"; then
    echo "错误: 需要 Node.js 20+，当前: $(node --version 2>/dev/null || '未安装')"
    exit 1
fi

# Install backend deps
echo "--- 安装后端依赖 ---"
cd "$PROJECT_DIR/backend"
pip3 install -q --user --break-system-packages -r requirements.txt
echo "后端依赖就绪"

# Install frontend deps
echo "--- 安装前端依赖 ---"
cd "$PROJECT_DIR/frontend"
[ ! -d "node_modules" ] && npm install
echo "前端依赖就绪"

# Start backend
echo "--- 启动后端 (端口 8000) ---"
cd "$PROJECT_DIR/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

sleep 2

# Start frontend
echo "--- 启动前端 (端口 3000) ---"
cd "$PROJECT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=== 启动完成 ==="
echo "打开浏览器访问: http://localhost:3000"
echo "默认账号: admin / admin123"
echo "按 Ctrl+C 停止"

cleanup() {
    echo "停止服务..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait 2>/dev/null
    echo "已停止"
    exit 0
}
trap cleanup SIGINT SIGTERM

wait
