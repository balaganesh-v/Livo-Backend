
import jwt

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session

from app.database.config import settings
from app.database.connection import get_database_session
from app.repositories.user_repository import UserRepository

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: Session = Depends(get_database_session),
):
    token = credentials.credentials

    try:
        token_data = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )

        user_id = int(token_data["sub"])

    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
        )

    repository = UserRepository(session)
    user = repository.get_user_by_id(user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User account is unavailable",
        )

    return user
