"""AI service - calls LLM API with streaming"""
import httpx
import json
from app.core.database import SessionLocal
from app.models.ai_config import AIConfig
from app.config import DEFAULT_API_BASE_URL, DEFAULT_API_KEY, DEFAULT_MODEL


def get_ai_config() -> AIConfig:
    """Get AI config from database, fallback to env defaults"""
    db = SessionLocal()
    try:
        config = db.query(AIConfig).first()
        if config:
            return config
    finally:
        db.close()

    # Return default config
    config = AIConfig(
        api_base_url=DEFAULT_API_BASE_URL,
        api_key=DEFAULT_API_KEY,
        model=DEFAULT_MODEL,
    )
    return config


async def stream_chat(messages: list[dict]):
    """Stream chat completion from LLM API (OpenAI-compatible)"""
    config = get_ai_config()

    if not config.api_key:
        yield "data: " + json.dumps({"error": "API Key 未配置，请在设置页面配置"}) + "\n\n"
        return

    url = f"{config.api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": messages,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                yield f"data: {json.dumps({'error': f'API 调用失败 ({resp.status_code}): {error_body.decode()}'})}\n\n"
                return

            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        yield "data: [DONE]\n\n"
                        return
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        # Support both "content" (standard) and "reasoning_content" (GLM thinking)
                        content = delta.get("content", "")
                        reasoning = delta.get("reasoning_content", "")
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
                        if reasoning:
                            yield f"data: {json.dumps({'reasoning': reasoning})}\n\n"
                    except json.JSONDecodeError:
                        continue
