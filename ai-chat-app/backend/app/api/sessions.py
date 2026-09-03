"""Session API"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_token
from app.models.session import Session as SessionModel
from app.models.message import Message
from app.schemas.schemas import (
    SessionCreate, SessionResponse, SessionUpdate, MessageResponse
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session_to_dict(s: SessionModel) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "system_prompt": s.system_prompt or "",
        "created_at": s.created_at.isoformat() if s.created_at else "",
        "updated_at": s.updated_at.isoformat() if s.updated_at else "",
    }


@router.get("")
def list_sessions(payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    user_id = int(payload["sub"])
    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.user_id == user_id)
        .order_by(SessionModel.updated_at.desc())
        .all()
    )
    return [_session_to_dict(s) for s in sessions]


@router.post("")
def create_session(
    req: SessionCreate,
    payload: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    user_id = int(payload["sub"])
    session = SessionModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=req.title,
        system_prompt=req.system_prompt,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_to_dict(session)


@router.get("/{session_id}/messages")
def get_messages(
    session_id: str,
    payload: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "session_id": m.session_id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else "",
        }
        for m in messages
    ]


@router.patch("/{session_id}")
def update_session(
    session_id: str,
    req: SessionUpdate,
    payload: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(404, "会话不存在")
    if req.title is not None:
        session.title = req.title
    if req.system_prompt is not None:
        session.system_prompt = req.system_prompt
    db.commit()
    return _session_to_dict(session)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    payload: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    db.query(Message).filter(Message.session_id == session_id).delete()
    db.query(SessionModel).filter(SessionModel.id == session_id).delete()
    db.commit()
    return {"ok": True}
