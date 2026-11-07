from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401
from app.controllers.ai_analysis_controller import router as ai_analysis_router
from app.controllers.chat_controller import router as chat_router
from app.controllers.app_controller import router as app_router
from app.controllers.auth_controller import router as auth_router
from app.controllers.file_content_controller import router as content_router
from app.controllers.scanner_controller import router as scanner_router
from app.controllers.source_folder_controller import router as source_folder_router
from app.controllers.workflow_controller import router as workflow_router
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(app_router)
app.include_router(auth_router)
app.include_router(scanner_router)
app.include_router(source_folder_router)
app.include_router(content_router)
app.include_router(ai_analysis_router)
app.include_router(chat_router)
app.include_router(workflow_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
