"""Authentication, token lifecycle, and protected-route tests."""

import hashlib
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app import models  # noqa: F401
from app.controllers.auth_controller import login_user, logout_user, register_user
from app.database.base import Base
from app.database.config import settings
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.schemas.auth_schema import LoginRequest, RegisterRequest
from app.security.authentication import get_current_user
from app.security.password_security import hash_password, verify_password
from app.services.auth_service import (AuthService, InvalidCredentialsError,
                                       InvalidRefreshTokenError,
                                       create_access_token,
                                       decode_access_token)
from app.services.user_service import UserAlreadyExistsError, UserService


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kwargs):
    return "INTEGER"


@compiles(BIGINT, "sqlite")
def _compile_mysql_bigint_for_sqlite(type_, compiler, **kwargs):
    return "INTEGER"


@pytest.fixture
def database_engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture(autouse=True)
def configured_test_signing_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-with-more-than-32-bytes")


def create_registered_user(
    database_session: Session,
    username: str = "sample-user",
    password: str = "StrongPassword123!",
) -> User:
    """Create a real Argon2id-backed account for authentication tests."""
    return UserService(database_session).register_user(
        username, f"{username}@example.com", password
    )


def make_request_with_cookie(cookie_value: str) -> Request:
    request_scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/auth/refresh",
        "raw_path": b"/api/auth/refresh",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"cookie", f"refresh_token={cookie_value}".encode())],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    return Request(request_scope)


def test_registration_hashes_password_and_returns_safe_profile(database_engine):
    registration_request = RegisterRequest(
        username="new-user",
        email="New.User@example.com",
        password="StrongPassword123!",
    )
    with Session(database_engine) as database_session:
        registered_profile = register_user(
            registration_request, UserService(database_session)
        )
        stored_user = database_session.scalar(select(User))

    assert registered_profile.username == "new-user"
    assert registered_profile.email == "new.user@example.com"
    assert not hasattr(registered_profile, "password_hash")
    assert stored_user.password_hash.startswith("$argon2id$")
    assert verify_password("StrongPassword123!", stored_user.password_hash)
    assert not verify_password("wrong-password", stored_user.password_hash)


def test_registration_rejects_duplicate_username_or_email(database_engine):
    with Session(database_engine) as database_session:
        user_service = UserService(database_session)
        user_service.register_user("duplicate-name", "first@example.com", "StrongPassword123!")
        with pytest.raises(UserAlreadyExistsError):
            user_service.register_user(
                "DUPLICATE-NAME", "second@example.com", "AnotherStrong123!"
            )
        with pytest.raises(UserAlreadyExistsError):
            user_service.register_user(
                "different-name", "FIRST@example.com", "AnotherStrong123!"
            )
        with pytest.raises(HTTPException) as duplicate_api_response:
            register_user(
                RegisterRequest(
                    username="duplicate-name",
                    email="third@example.com",
                    password="AnotherStrong123!",
                ),
                user_service,
            )
        assert duplicate_api_response.value.status_code == 409
        assert database_session.scalar(select(func.count()).select_from(User)) == 1


def test_registration_schema_rejects_invalid_email_and_weak_password():
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="short",
            email="not-an-email",
            password="weak-password",
        )
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="valid-name",
            email="valid@example.com",
            password="weak-password-only",
        )


def test_login_accepts_email_or_username_and_rejects_wrong_credentials(
    database_engine,
):
    with Session(database_engine) as database_session:
        registered_user = create_registered_user(database_session)
        auth_service = AuthService(database_session)
        assert auth_service.authenticate_user(
            registered_user.email, "StrongPassword123!"
        ).id == registered_user.id
        assert auth_service.authenticate_user(
            registered_user.username, "StrongPassword123!"
        ).id == registered_user.id
        with pytest.raises(InvalidCredentialsError):
            auth_service.authenticate_user(registered_user.email, "incorrect-password")

        login_response = login_user(
            LoginRequest(
                identifier=registered_user.username,
                password="StrongPassword123!",
            ),
            Response(),
            auth_service,
        )
        assert login_response.access_token
        assert login_response.user.id == registered_user.id


def test_plain_text_legacy_password_is_not_accepted(database_engine):
    with Session(database_engine) as database_session:
        legacy_user = User(
            name="legacy-user",
            username="legacy-user",
            email="legacy@example.com",
            password_hash="StrongPassword123!",
            is_active=True,
        )
        database_session.add(legacy_user)
        database_session.commit()
        with pytest.raises(InvalidCredentialsError):
            AuthService(database_session).authenticate_user(
                legacy_user.email, "StrongPassword123!"
            )


def test_access_token_rejects_expired_malformed_wrong_signature_and_wrong_claims(
):
    now = datetime.now(timezone.utc)
    expired_token = jwt.encode(
        {
            "sub": "1",
            "sid": 1,
            "iss": "ai-folder-organizer",
            "type": "access",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=1),
            "jti": "expired-token",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    wrong_signature_token = jwt.encode(
        {
            "sub": "1",
            "sid": 1,
            "iss": "ai-folder-organizer",
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "jti": "wrong-signature",
        },
        "a-different-secret-with-at-least-32-bytes",
        algorithm="HS256",
    )
    wrong_claim_token = jwt.encode(
        {"sub": "1", "sid": 1, "iss": "wrong-issuer", "type": "refresh"},
        settings.jwt_secret,
        algorithm="HS256",
    )

    for invalid_token in (
        expired_token,
        wrong_signature_token,
        wrong_claim_token,
        "malformed.jwt.value",
    ):
        with pytest.raises(jwt.PyJWTError):
            decode_access_token(invalid_token)


def test_current_user_dependency_requires_valid_token_and_active_user(database_engine):
    with Session(database_engine) as database_session:
        registered_user = create_registered_user(database_session)
        issued_token_pair = AuthService(database_session).create_token_pair(
            registered_user
        )
        valid_token = issued_token_pair.access_token
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=valid_token
        )
        assert get_current_user(credentials, database_session).id == registered_user.id

        invalid_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="invalid"
        )
        with pytest.raises(HTTPException) as unauthorized:
            get_current_user(invalid_credentials, database_session)
        assert unauthorized.value.status_code == 401

        registered_user.is_active = False
        database_session.commit()
        with pytest.raises(HTTPException) as inactive_user:
            get_current_user(credentials, database_session)
        assert inactive_user.value.status_code == 401


def test_refresh_rotation_revokes_old_token_and_logout_revokes_replacement(
    database_engine,
):
    with Session(database_engine) as database_session:
        registered_user = create_registered_user(database_session)
        auth_service = AuthService(database_session)
        first_token_pair = auth_service.create_token_pair(registered_user)
        first_session = database_session.scalar(select(RefreshSession))
        assert first_session.token_hash == hashlib.sha256(
            first_token_pair.refresh_token.encode()
        ).hexdigest()
        assert first_token_pair.refresh_token not in first_session.token_hash

        second_token_pair = auth_service.rotate_refresh_token(
            first_token_pair.refresh_token
        )
        with pytest.raises(InvalidRefreshTokenError):
            auth_service.rotate_refresh_token(first_token_pair.refresh_token)

        logout_response = logout_user(
            make_request_with_cookie(second_token_pair.refresh_token), auth_service
        )
        assert logout_response.status_code == 204
        with pytest.raises(InvalidRefreshTokenError):
            auth_service.rotate_refresh_token(second_token_pair.refresh_token)

        revoked_access_credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=second_token_pair.access_token
        )
        with pytest.raises(HTTPException) as revoked_access:
            get_current_user(revoked_access_credentials, database_session)
        assert revoked_access.value.status_code == 401


def test_refresh_http_route_rotates_http_only_cookie(database_engine):
    from app.controllers.auth_controller import refresh_access_token

    with Session(database_engine) as database_session:
        registered_user = create_registered_user(database_session)
        auth_service = AuthService(database_session)
        first_token_pair = auth_service.create_token_pair(registered_user)
        response = Response()
        rotated_token_response = refresh_access_token(
            make_request_with_cookie(first_token_pair.refresh_token),
            response,
            auth_service,
        )
        assert rotated_token_response.access_token
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "path=/api/auth" in response.headers["set-cookie"].lower()


def test_auth_openapi_protects_file_routes_and_keeps_signup_public():
    from app.main import app

    api_paths = app.openapi()["paths"]
    assert "/api/auth/register" in api_paths
    assert "/api/auth/login" in api_paths
    assert "/api/auth/refresh" in api_paths
    assert "/api/auth/logout" in api_paths
    assert "/api/auth/me" in api_paths
    assert api_paths["/api/scans"]["post"].get("security")
    assert api_paths["/api/files/{file_id}/extract-content"]["post"].get("security")
    assert not api_paths["/api/auth/register"]["post"].get("security")
    assert "/api/users/dev" not in api_paths


def test_user_registration_database_failure_rolls_back(database_engine):
    with Session(database_engine) as database_session:
        def reject_user_commit(_database_session):
            raise SQLAlchemyError("simulated account write failure")

        event.listen(database_session, "before_commit", reject_user_commit)
        try:
            with pytest.raises(SQLAlchemyError):
                UserService(database_session).register_user(
                    "rollback-user", "rollback@example.com", "StrongPassword123!"
                )
        finally:
            event.remove(database_session, "before_commit", reject_user_commit)

    with Session(database_engine) as verification_session:
        assert verification_session.scalar(select(func.count()).select_from(User)) == 0


def test_password_hash_verifier_rejects_malformed_hash():
    assert not verify_password("any-password", "not-an-argon-hash")
