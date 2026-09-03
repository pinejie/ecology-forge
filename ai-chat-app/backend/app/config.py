"""AI Chat App - Backend Config"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'chat.db'}")

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72

# Default AI config (can be overridden from database)
DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
DEFAULT_API_KEY = os.getenv("API_KEY", "")
DEFAULT_MODEL = os.getenv("AI_MODEL", "glm-4-flash")

# App
APP_NAME = "AI Chat App"
APP_VERSION = "0.1.0"
