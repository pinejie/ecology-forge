#!/bin/bash
# 数据库环境切换脚本
# 用法: switch-env.sh vpn|office

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PWD_FILE="$SCRIPT_DIR/pwd.md"

if [ -z "$1" ]; then
  echo "用法: switch-env.sh vpn|office"
  echo ""
  echo "  vpn    — 家中/VPN环境 (127.0.0.1:11433)"
  echo "  office — 公司环境 (172.18.28.108:1433)"
  exit 1
fi

case "$1" in
  vpn)
    HOST="127.0.0.1"
    PORT="11433"
    ;;
  office)
    HOST="172.18.28.108"
    PORT="1433"
    ;;
  *)
    echo "未知环境: $1"
    echo "支持的环境: vpn, office"
    exit 1
    ;;
esac

cat > "$PWD_FILE" << EOF
# 数据库连接配置

- **host**: $HOST
- **port**: $PORT
- **user**: sa
- **password**: Weaver@2001
- **database**: ecology
EOF

echo "已切换到 $1 环境: $HOST:$PORT"
