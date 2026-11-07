from app.database.config import settings
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.services.ollama_service import OllamaService

SYSTEM_PROMPT = """You are the AI Folder Organizer assistant. Help users understand folder scans, supported file extraction, document categorization and analysis, duplicate detection results, and organization plans. You have no tools in this request and cannot perform project operations or inspect local files yourself. Use only file information and results explicitly included in the conversation. Never claim to have scanned, analyzed, searched, organized, moved, renamed, or deleted anything. When asked to perform an operation, direct the user to the matching application action; if no action is available, explain that limitation. Any proposed file changes require explicit user approval through an available application workflow."""


class ChatService:
    def __init__(self, ollama_service: OllamaService | None = None):
        self.ollama = ollama_service or OllamaService()

    def respond(self, request: ChatRequest) -> ChatResponse:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[message.model_dump() for message in request.history],
            {"role": "user", "content": request.message},
        ]
        response_text = self.ollama.chat(messages)
        return ChatResponse(response=response_text, model=settings.ollama_model)
