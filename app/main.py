from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401
from app.controllers.scanner_controller import router as scanner_router
from app.controllers.system_controller import router as system_router
from app.database.base import Base
from app.database.connection import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        print("❌ Database connection failed")
        raise

    print("✅ Database connection established")
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="AI Folder Organizer API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(system_router)
app.include_router(scanner_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
