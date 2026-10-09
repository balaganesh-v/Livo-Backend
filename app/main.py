import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.controllers.ai_analysis_controller import router as ai_analysis_router
from app.controllers.scanner_controller import router as scanner_router
from app.controllers.system_controller import router as system_router
from app.database.connection import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Verify required infrastructure before accepting requests."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database connection failed during startup")
        raise

    print("✅ Database connection established")
    yield


app = FastAPI(
    title="AI Folder Organizer API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(scanner_router)
app.include_router(ai_analysis_router)
app.include_router(system_router)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
