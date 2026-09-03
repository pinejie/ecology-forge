"""Pydantic schemas"""
from pydantic import BaseModel
from typing import Optional


# Auth
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str


# Chat
class ChatRequest(BaseModel):
    session_id: str
    message: str


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str


# Session
class SessionCreate(BaseModel):
    title: Optional[str] = "新对话"
    system_prompt: Optional[str] = ""


class SessionResponse(BaseModel):
    id: str
    title: str
    system_prompt: str
    created_at: str
    updated_at: str


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    system_prompt: Optional[str] = None


# AI Config
class AIConfigRequest(BaseModel):
    api_base_url: str
    api_key: str
    model: str


class AIConfigResponse(BaseModel):
    api_base_url: str
    api_key: str  # masked in response
    model: str
