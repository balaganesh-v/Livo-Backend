from fastapi import FastAPI

app = FastAPI(
    title="AI Folder Organizer API",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "message": "AI Folder Organizer API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }