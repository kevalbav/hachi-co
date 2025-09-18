from fastapi import Header, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .config import settings

# Use the consistent property name from settings
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_api_key(x_api_key: str | None = Header(default=None)):
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")