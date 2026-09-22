from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)

__all__ = ["SessionLocal", "engine"]
