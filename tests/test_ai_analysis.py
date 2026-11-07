import json

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.database.base import Base
from app.models.file import File
from app.models.file_ai_analysis import FileAIAnalysis
from app.models.file_content import FileContent
from app.models.source_folder import SourceFolder
from app.models.user import User
from app.schemas.ai_analysis_schema import AIAnalysisResult
from app.services.ai_analysis_service import (
    AIAnalysisService,
    EmptyExtractedContentError,
    ExtractedContentUnavailableError,
    ExtractionFailedError,
    FileNotFoundForAnalysisError,
)
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaService,
    OllamaTimeoutError,
)


@compiles(BigInteger, "sqlite")
@compiles(BIGINT, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kwargs):
    return "INTEGER"


@compiles(LONGTEXT, "sqlite")
def _compile_longtext_for_sqlite(type_, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def database_session():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


class FakeOllama:
    def __init__(self, result=None, error=None, results=None, fail_text=None):
        self.result = result or AIAnalysisResult(
            category="study_materials",
            subcategory="lecture_notes",
            description="Notes about biology and cell structure.",
            keywords=["biology", "cells", "notes"],
            confidence=0.9,
            content_type="text_document",
            model_used="gemma3:4b",
        )
        self.error = error
        self.results = results or {}
        self.fail_text = fail_text
        self.calls = []

    def analyze(self, text, metadata=None):
        self.calls.append((text, metadata))
        if self.fail_text == text:
            raise OllamaResponseError
        if self.error:
            raise self.error
        return self.results.get(text, self.result)


def add_file(session, user_id, content_status="completed", text="Biology lecture notes about cells.", source_folder_id=None):
    if source_folder_id is None:
        folder_index = session.scalar(select(func.count()).select_from(SourceFolder)) + 1
        folder_path = f"/docs-{folder_index}"
        folder = SourceFolder(user_id=user_id, name="docs", folder_path=folder_path, status="completed")
        session.add(folder)
        session.flush()
        source_folder_id = folder.id
    else:
        folder_path = session.get(SourceFolder, source_folder_id).folder_path
    file = File(user_id=user_id, source_folder_id=source_folder_id, name="notes.txt", file_path=f"{folder_path}/notes-{session.scalar(select(func.count()).select_from(File)) + 1}.txt")
    session.add(file)
    session.flush()
    if content_status is not None:
        session.add(FileContent(file_id=file.id, extraction_status=content_status, extracted_text=text))
        session.flush()
    return file


def test_analysis_persists_and_reanalysis_updates_same_record(database_session):
    owner = User(name="Owner", email="owner@example.com", password_hash="unused")
    database_session.add(owner)
    database_session.flush()
    file = add_file(database_session, owner.id)

    service = AIAnalysisService(database_session, FakeOllama())
    first = service.analyze_file(file.id, owner.id)
    first_id = first.id
    second = service.analyze_file(file.id, owner.id)

    assert second.id == first_id
    assert second.category == "study_materials"
    assert second.keywords == ["biology", "cells", "notes"]
    assert float(second.confidence) == 0.9
    assert database_session.scalar(select(func.count()).select_from(FileAIAnalysis)) == 1


def test_file_ownership_content_status_and_empty_text_are_checked(database_session):
    owner = User(name="Owner", email="owner2@example.com", password_hash="unused")
    other = User(name="Other", email="other@example.com", password_hash="unused")
    database_session.add_all([owner, other])
    database_session.flush()
    file = add_file(database_session, owner.id)
    service = AIAnalysisService(database_session, FakeOllama())
    with pytest.raises(FileNotFoundForAnalysisError):
        service.analyze_file(987654, owner.id)
    with pytest.raises(FileNotFoundForAnalysisError):
        service.analyze_file(file.id, other.id)

    missing = add_file(database_session, owner.id, content_status=None)
    with pytest.raises(ExtractedContentUnavailableError):
        service.analyze_file(missing.id, owner.id)

    failed = add_file(database_session, owner.id, content_status="failed")
    with pytest.raises(ExtractionFailedError):
        service.analyze_file(failed.id, owner.id)

    empty = add_file(database_session, owner.id, text="  \n")
    with pytest.raises(EmptyExtractedContentError):
        service.analyze_file(empty.id, owner.id)


def test_analysis_database_failure_rolls_back(database_session):
    owner = User(name="Owner", email="rollback@example.com", password_hash="unused")
    database_session.add(owner)
    database_session.flush()
    file = add_file(database_session, owner.id)

    def reject_commit(_session):
        raise SQLAlchemyError("simulated analysis persistence failure")

    event.listen(database_session, "before_commit", reject_commit)
    try:
        with pytest.raises(SQLAlchemyError):
            AIAnalysisService(database_session, FakeOllama()).analyze_file(
                file.id, owner.id
            )
    finally:
        event.remove(database_session, "before_commit", reject_commit)
    assert database_session.scalar(select(func.count()).select_from(FileAIAnalysis)) == 0


def test_extraction_pending_status_is_unavailable(database_session):
    owner = User(name="Owner", email="owner3@example.com", password_hash="unused")
    database_session.add(owner)
    database_session.flush()
    file = add_file(database_session, owner.id, content_status="pending")
    with pytest.raises(ExtractedContentUnavailableError):
        AIAnalysisService(database_session, FakeOllama()).analyze_file(file.id, owner.id)


def test_bulk_processes_all_files_and_skips_unusable_content(database_session):
    owner = User(name="Owner", email="bulk@example.com", password_hash="unused")
    database_session.add(owner)
    database_session.flush()
    first = add_file(database_session, owner.id, text="First document text.")
    folder_id = first.source_folder_id
    second = add_file(database_session, owner.id, text="Second document text.", source_folder_id=folder_id)
    add_file(database_session, owner.id, text="", source_folder_id=folder_id)
    add_file(database_session, owner.id, content_status="unsupported", text=None, source_folder_id=folder_id)
    first_result = AIAnalysisResult(category="study_materials", subcategory="notes", description="First analysis", keywords=["first"], confidence=0.8, content_type="text", model_used="gemma3:4b")
    second_result = AIAnalysisResult(category="work_documents", subcategory="memo", description="Second analysis", keywords=["second"], confidence=0.7, content_type="text", model_used="gemma3:4b")
    ollama = FakeOllama(results={"First document text.": first_result, "Second document text.": second_result})

    response = AIAnalysisService(database_session, ollama).analyze_source_folder(folder_id, owner.id)

    assert response["total_files"] == 4
    assert response["eligible_files"] == response["analyzed_files"] == 2
    assert len(ollama.calls) == 2
    assert {row.file_id: row.category for row in database_session.scalars(select(FileAIAnalysis))} == {
        first.id: "study_materials",
        second.id: "work_documents",
    }
    assert len(response["skipped_files"]) == 2


def test_bulk_skips_existing_by_default_and_reanalysis_updates(database_session):
    owner = User(name="Owner", email="bulk-reanalyze@example.com", password_hash="unused")
    database_session.add(owner)
    database_session.flush()
    file = add_file(database_session, owner.id)
    folder_id = file.source_folder_id
    initial = AIAnalysisService(database_session, FakeOllama()).analyze_file(file.id, owner.id)
    initial_id = initial.id
    updated_result = AIAnalysisResult(category="other", subcategory="reference", description="Updated", keywords=["updated"], confidence=0.6, content_type="text", model_used="gemma3:4b")
    ollama = FakeOllama(result=updated_result)
    service = AIAnalysisService(database_session, ollama)

    skipped = service.analyze_source_folder(folder_id, owner.id)
    updated = service.analyze_source_folder(folder_id, owner.id, reanalyze=True)

    assert skipped["analyzed_files"] == 0
    assert skipped["skipped_files"][0]["reason"] == "Already analyzed."
    assert updated["analyzed_file_ids"] == [file.id]
    saved = database_session.scalar(select(FileAIAnalysis).where(FileAIAnalysis.file_id == file.id))
    assert saved.id == initial_id
    assert saved.description == "Updated"
    assert database_session.scalar(select(func.count()).select_from(FileAIAnalysis)) == 1


def test_bulk_isolates_analysis_failure_and_rejects_other_users_folder(database_session):
    owner = User(name="Owner", email="bulk-errors@example.com", password_hash="unused")
    other = User(name="Other", email="bulk-other@example.com", password_hash="unused")
    database_session.add_all([owner, other])
    database_session.flush()
    first = add_file(database_session, owner.id, text="Bad item")
    folder_id = first.source_folder_id
    add_file(database_session, owner.id, text="Good item", source_folder_id=folder_id)
    first_text = database_session.scalar(select(FileContent.extracted_text).where(FileContent.file_id == first.id))
    good = AIAnalysisResult(category="other", subcategory="reference", description="Good", keywords=["good"], confidence=0.8, content_type="text", model_used="gemma3:4b")
    ollama = FakeOllama(result=good, fail_text=first_text)
    service = AIAnalysisService(database_session, ollama)

    result = service.analyze_source_folder(folder_id, owner.id)
    assert len(result["failed_files"]) == 1
    assert result["analyzed_files"] == 1
    assert database_session.scalar(select(func.count()).select_from(FileAIAnalysis)) == 1
    with pytest.raises(FileNotFoundForAnalysisError):
        service.analyze_source_folder(folder_id, other.id)


def test_analysis_schema_validates_category_and_confidence():
    valid = dict(category="other", subcategory="misc", description="A document", keywords=["doc"], confidence=0.5, content_type="text", model_used="gemma3:4b")
    assert AIAnalysisResult(**valid).confidence == 0.5
    for invalid in (
        {**valid, "category": "unknown"},
        {**valid, "confidence": 1.1},
        {**valid, "subcategory": ""},
    ):
        with pytest.raises(ValidationError):
            AIAnalysisResult(**invalid)


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        pass

    def json(self):
        return self.value


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request = None

    def post(self, url, json):
        self.request = (url, json)
        if self.error:
            raise self.error
        return FakeResponse(self.response)


def test_ollama_structured_request_and_invalid_output():
    result = {"category": "study_materials", "subcategory": "lecture_notes", "description": "Biology notes", "keywords": ["biology"], "confidence": 0.9, "content_type": "text_document", "model_used": "gemma3:4b"}
    client = FakeClient({"response": json.dumps(result)})
    parsed = OllamaService(client).analyze("Some extracted text")
    assert parsed.category == "study_materials"
    assert client.request[1]["stream"] is False
    assert client.request[1]["format"]["type"] == "object"

    with pytest.raises(OllamaResponseError):
        OllamaService(FakeClient({"response": "not json"})).analyze("text")
    with pytest.raises(OllamaResponseError):
        OllamaService(FakeClient({"response": json.dumps({**result, "model_used": "wrong"})})).analyze("text")


def test_ollama_timeout_and_connection_errors_are_mapped():
    with pytest.raises(OllamaTimeoutError):
        OllamaService(FakeClient(error=httpx.TimeoutException("timeout"))).analyze("text")
    with pytest.raises(OllamaConnectionError):
        OllamaService(FakeClient(error=httpx.ConnectError("offline"))).analyze("text")
