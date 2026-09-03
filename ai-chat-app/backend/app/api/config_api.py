"""AI Config API - runtime configurable"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_token
from app.models.ai_config import AIConfig
from app.schemas.schemas import AIConfigRequest, AIConfigResponse
from app.config import DEFAULT_API_BASE_URL, DEFAULT_API_KEY, DEFAULT_MODEL

router = APIRouter(prefix="/api/config", tags=["config"])


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


@router.get("/ai", response_model=AIConfigResponse)
def get_ai_config(payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    config = db.query(AIConfig).first()
    if not config:
        return AIConfigResponse(
            api_base_url=DEFAULT_API_BASE_URL,
            api_key=_mask_key(DEFAULT_API_KEY) if DEFAULT_API_KEY else "",
            model=DEFAULT_MODEL,
        )
    return AIConfigResponse(
        api_base_url=config.api_base_url,
        api_key=_mask_key(config.api_key),
        model=config.model,
    )


@router.put("/ai", response_model=AIConfigResponse)
def update_ai_config(
    req: AIConfigRequest,
    payload: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    config = db.query(AIConfig).first()
    if not config:
        config = AIConfig(
            api_base_url=req.api_base_url,
            api_key=req.api_key,
            model=req.model,
        )
        db.add(config)
    else:
        # If api_key is masked (contains ****), don't update it
        if "****" not in req.api_key:
            config.api_key = req.api_key
        config.api_base_url = req.api_base_url
        config.model = req.model
    db.commit()
    db.refresh(config)
    return AIConfigResponse(
        api_base_url=config.api_base_url,
        api_key=_mask_key(config.api_key),
        model=config.model,
    )
