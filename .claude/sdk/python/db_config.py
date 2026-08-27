"""
数据库配置读取——统一从 pwd.md 读取，不再依赖环境变量。
所有 SDK 的 __init__ 都通过本模块获取连接参数。
"""

import os


def load_db_config():
    """
    从 .claude/sdk/pwd.md 读取数据库连接配置。
    返回 dict: {"host": ..., "port": ..., "user": ..., "password": ..., "database": ...}
    """
    pwd_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pwd.md")
    if not os.path.exists(pwd_path):
        raise FileNotFoundError(
            f"数据库配置文件不存在: {pwd_path}\n"
            "请先在 .claude/sdk/pwd.md 中写入 host/user/password/database"
        )

    config = {}
    with open(pwd_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip("- ").strip()
            if line.startswith("**") and "**:" in line:
                key = line.split("**")[1].strip()
                val = line.split("**:")[1].strip()
                config[key] = val

    required = ["host", "user", "password", "database"]
    missing = [k for k in required if k not in config]
    if missing:
        raise ValueError(
            f"pwd.md 缺少必填字段: {', '.join(missing)}\n"
            f"当前读取到的: {list(config.keys())}"
        )

    return {
        "host": config["host"],
        "port": int(config.get("port", "1433")),
        "user": config["user"],
        "password": config["password"],
        "database": config["database"],
    }
