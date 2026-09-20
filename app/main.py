import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import models  # noqa: F401
from database.base import Base
from database.connection import engine

app = FastAPI(
    title="AI Folder Organizer API",
    version="1.0.0",
)


@app.on_event("startup")
async def startup():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        Base.metadata.create_all(bind=engine)

        print("✅ Database connected successfully")

    except SQLAlchemyError as exc:
        print(f"❌ Database connection failed: {exc}")


@app.get("/")
def root():
    return {"message": "AI Folder Organizer API is running"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
