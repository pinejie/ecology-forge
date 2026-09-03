"""AI config model - stores runtime-configurable API settings"""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class AIConfig(Base):
    __tablename__ = "ai_config"

    id = Column(Integer, primary_key=True)
    api_base_url = Column(String(500), nullable=False)
    api_key = Column(Text, nullable=False)  # encrypted in production
    model = Column(String(100), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
