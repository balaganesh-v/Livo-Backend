from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.config import settings


# Create the database connection
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)


# Create a factory to generate database sessions
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# Get a database session for each request
def get_database_session() -> Generator[Session, None, None]:
    database = SessionLocal()

    try:
        yield database
    finally:
        database.close()


# Make these available for other files
__all__ = ["engine", "SessionLocal", "get_database_session"]