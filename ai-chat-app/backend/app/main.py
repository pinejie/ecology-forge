"""FastAPI main entry"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.sessions import router as sessions_router
from app.api.config_api import router as config_router
from app.config import APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(config_router)


@app.on_event("startup")
def startup():
    init_db()
    # Create default admin user if no users exist
    from app.core.database import SessionLocal
    from app.models.user import User
    from passlib.context import CryptContext

    db = SessionLocal()
    try:
        if not db.query(User).first():
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            admin = User(username="admin", password_hash=pwd_context.hash("admin123"))
            db.add(admin)
            db.commit()
            print("默认管理员账号已创建: admin / admin123")
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
