import httpx
import pytest
from fastapi import HTTPException

from app.controllers import chat_controller
from app.services.chat_service import ChatService
from app.schemas.chat_schema import ChatRequest, ChatResponse
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaService,
    OllamaTimeoutError,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://ollama/api/chat")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("request failed", request=request, response=response)

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.closed = False

    def post(self, url, json):
        self.calls.append((url, json))
        if self.error:
            raise self.error
        return self.response


def test_ollama_chat_uses_configured_model_and_returns_actual_content():
    from app.database.config import settings

    client = FakeClient(FakeResponse({"message": {"role": "assistant", "content": "Hello from the model."}}))
    result = OllamaService(client).chat([{"role": "user", "content": "Hello"}])

    url, request = client.calls[0]
    assert url.endswith("/api/chat")
    assert request["model"] == settings.ollama_model
    assert request["stream"] is False
    assert result == "Hello from the model."


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ConnectError("offline"), OllamaConnectionError),
        (httpx.ReadTimeout("timeout"), OllamaTimeoutError),
    ],
)
def test_ollama_chat_maps_connection_and_timeout_errors(error, expected):
    with pytest.raises(expected):
        OllamaService(FakeClient(error=error)).chat([])


def test_ollama_chat_maps_missing_model_and_invalid_payload():
    model_error = FakeResponse({"error": "model not found"}, status_code=404)
    with pytest.raises(OllamaModelNotFoundError):
        OllamaService(FakeClient(model_error)).chat([])

    with pytest.raises(OllamaResponseError):
        OllamaService(FakeClient(FakeResponse({"message": {"content": "  "}}))).chat([])


def test_chat_request_rejects_system_role_and_oversized_history():
    with pytest.raises(ValueError):
        ChatRequest.model_validate({"message": "hello", "history": [{"role": "system", "content": "bad"}]})
    with pytest.raises(ValueError):
        ChatRequest.model_validate({"message": "hello", "history": [{"role": "user", "content": "x"}] * 21})
    with pytest.raises(ValueError):
        ChatRequest.model_validate({"message": "   "})


def test_chat_service_adds_folder_organizer_context_and_history():
    class FakeOllama:
        def __init__(self):
            self.messages = None

        def chat(self, messages):
            self.messages = messages
            return "Helpful response"

    ollama = FakeOllama()
    response = ChatService(ollama).respond(ChatRequest(
        message="What can you organize?",
        history=[{"role": "user", "content": "Hello"}],
    ))

    assert response.response == "Helpful response"
    assert ollama.messages[0]["role"] == "system"
    assert "AI Folder Organizer" in ollama.messages[0]["content"]
    assert ollama.messages[1:] == [
        {"role": "user", "content": "Hello"},
        {"role": "user", "content": "What can you organize?"},
    ]


def test_authenticated_chat_route_returns_response(monkeypatch):
    monkeypatch.setattr(
        chat_controller,
        "ChatService",
        lambda: type("FakeChat", (), {"respond": lambda self, request: ChatResponse(response="Real reply", model="gemma3:4b")})(),
    )

    result = chat_controller.create_chat_response(ChatRequest(message="Hi"), object())
    assert result.model_dump() == {"response": "Real reply", "model": "gemma3:4b"}
    route = chat_controller.router.routes[0]
    assert route.path == "/api/chat"
    assert route.dependant.dependencies


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (OllamaConnectionError(), 503),
        (OllamaModelNotFoundError(), 503),
        (OllamaTimeoutError(), 504),
        (OllamaResponseError(), 502),
    ],
)
def test_chat_route_maps_ollama_errors(monkeypatch, error, status_code):
    monkeypatch.setattr(
        chat_controller,
        "ChatService",
        lambda: type("FailingChat", (), {"respond": lambda self, request: (_ for _ in ()).throw(error)})(),
    )
    with pytest.raises(HTTPException) as raised:
        chat_controller.create_chat_response(ChatRequest(message="Hi"), object())
    assert raised.value.status_code == status_code
