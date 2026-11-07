from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.mysql import BIGINT, LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.controllers.source_folder_controller import process_source_folder_files
from app.database.base import Base
from app.models.file import File
from app.models.file_ai_analysis import FileAIAnalysis
from app.models.file_content import FileContent
from app.models.source_folder import SourceFolder, SourceFolderStatus
from app.models.user import User
from app.schemas.ai_analysis_schema import AIAnalysisResult
from app.services import ai_analysis_service
from app.services.ollama_service import OllamaResponseError


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
    def analyze(self, text, metadata=None):
        if "AI failure" in text:
            raise OllamaResponseError
        return AIAnalysisResult(
            category="study_materials",
            subcategory="notes",
            description="Study notes",
            keywords=["notes"],
            confidence=0.9,
            content_type="text_document",
            model_used="test-model",
        )


def _add_folder_and_files(session: Session, root: Path, user: User):
    root.mkdir()
    folder = SourceFolder(
        user_id=user.id,
        name=root.name,
        folder_path=str(root),
        status=SourceFolderStatus.COMPLETED,
    )
    session.add(folder)
    session.flush()

    records = []
    for name, content in (
        ("first.txt", "First file content"),
        ("failed-ai.txt", "AI failure content"),
        ("second.txt", "Second file content"),
        ("archive.zip", "unsupported content"),
    ):
        path = root / name
        path.write_text(content, encoding="utf-8")
        record = File(
            user_id=user.id,
            source_folder_id=folder.id,
            name=name,
            file_path=str(path),
            extension=path.suffix,
        )
        session.add(record)
        records.append(record)
    session.commit()
    return folder, records


def test_processes_each_file_and_persists_extraction_and_analysis(
    database_session, tmp_path, monkeypatch
):
    user = User(
        name="Folder Owner",
        username="folder-owner",
        email="folder-owner@example.com",
        password_hash="unused",
        is_active=True,
    )
    database_session.add(user)
    database_session.commit()
    folder, files = _add_folder_and_files(database_session, tmp_path / "source", user)
    monkeypatch.setattr(ai_analysis_service, "OllamaService", FakeOllama)

    response = process_source_folder_files(folder.id, database_session, user)

    assert response.source_folder_id == folder.id
    assert response.total_files == 4
    assert response.extracted_files == 3
    assert response.categorized_files == 2
    assert response.unsupported_files == 1
    assert response.failed_files == 1
    assert {result.file_id for result in response.results} == {file.id for file in files}
    assert {result.category for result in response.results if result.category} == {"study_materials"}
    assert database_session.scalar(select(FileContent).where(FileContent.file_id == files[0].id)).extracted_text == "First file content"
    saved_analyses = list(database_session.scalars(select(FileAIAnalysis)))
    assert len(saved_analyses) == 2
    assert all(analysis.category == "study_materials" for analysis in saved_analyses)


def test_process_source_folder_rejects_folder_owned_by_another_user(
    database_session, tmp_path
):
    owner = User(name="Owner", email="owner@example.com", password_hash="unused")
    other_user = User(name="Other", email="other@example.com", password_hash="unused")
    database_session.add_all([owner, other_user])
    database_session.commit()
    folder, _ = _add_folder_and_files(database_session, tmp_path / "private", owner)

    with pytest.raises(HTTPException) as error:
        process_source_folder_files(folder.id, database_session, other_user)

    assert error.value.status_code == 404
