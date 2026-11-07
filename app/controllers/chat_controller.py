from fastapi import APIRouter, Depends, HTTPException

from app.database.config import settings
from app.models.user import User
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.security.authentication import get_current_user
from app.services.chat_service import ChatService
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
def create_chat_response(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    # Authentication is required; the chat itself is not persisted.
    _ = current_user
    try:
        return ChatService().respond(request)
    except OllamaModelNotFoundError:
        raise HTTPException(
            status_code=503,
            detail=f"The configured Ollama model '{settings.ollama_model}' is unavailable. Pull the configured model and try again.",
        )
    except OllamaTimeoutError:
        raise HTTPException(status_code=504, detail="Ollama did not respond before the request timed out.")
    except OllamaConnectionError:
        raise HTTPException(status_code=503, detail="Cannot connect to Ollama. Start Ollama and try again.")
    except OllamaResponseError:
        raise HTTPException(status_code=502, detail="Ollama returned an invalid chat response.")
