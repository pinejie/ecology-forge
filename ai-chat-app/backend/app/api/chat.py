"""Chat API with SSE streaming"""
import uuid
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_token
from app.models.session import Session as SessionModel
from app.models.message import Message
from app.schemas.schemas import ChatRequest
from app.services.ai_service import stream_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/completions")
async def chat_completions(
    req: ChatRequest,
    payload: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    # Verify session exists
    session = db.query(SessionModel).filter(SessionModel.id == req.session_id).first()
    if not session:
        raise HTTPException(404, "会话不存在")

    # Save user message
    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=req.session_id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    db.commit()

    # Build message history for API call
    history = []
    if session.system_prompt:
        history.append({"role": "system", "content": session.system_prompt})

    # Load recent messages (last 20 for context window)
    recent = (
        db.query(Message)
        .filter(Message.session_id == req.session_id)
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    recent.reverse()
    for m in recent:
        history.append({"role": m.role, "content": m.content})

    async def generate():
        full_content = ""
        async for chunk in stream_chat(history):
            yield chunk
            # Parse content for saving
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                try:
                    data = json.loads(chunk[6:])
                    if "content" in data:
                        full_content += data["content"]
                    elif "error" in data:
                        return
                except json.JSONDecodeError:
                    pass

        # Save assistant message to database
        if full_content:
            db2 = Session()
            try:
                assistant_msg = Message(
                    id=str(uuid.uuid4()),
                    session_id=req.session_id,
                    role="assistant",
                    content=full_content,
                )
                db2.add(assistant_msg)
                # Update session title if it's the first exchange
                if session.title == "新对话":
                    session.title = req.message[:30]
                db2.commit()
            finally:
                db2.close()

    return StreamingResponse(generate(), media_type="text/event-stream")
