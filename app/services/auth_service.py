
from datetime import datetime, timedelta, timezone

import jwt

from app.database.config import settings
from app.repositories.user_repository import UserRepository
from app.security.password_security import verify_password


class InvalidCredentialsError(Exception):
    """Raised when login credentials are invalid."""


class AuthService:
    def __init__(self, session):
        self.session = session
        self.repository = UserRepository(session)

    def login(self, identifier: str, password: str):
        """Authenticate a user by username or email and password.

        Returns the User on success, raises InvalidCredentialsError otherwise.
        """
        identifier = identifier.strip()
        user = self.repository.get_user_by_email_or_username(identifier)

        if user is None or not user.is_active:
            raise InvalidCredentialsError("Invalid credentials")

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid credentials")

        return user

    def create_access_token(self, user_id: int) -> str:
        """Create a signed JWT access token for the given user ID."""
        expiry = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_minutes
        )
        payload = {
            "sub": str(user_id),
            "exp": expiry,
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
