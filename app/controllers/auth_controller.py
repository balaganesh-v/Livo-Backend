
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_database_session
from app.schemas.auth_schema import RegisterRequest, LoginRequest, LoginResponse
from app.schemas.user_schema import UserResponse
from app.services.user_service import UserService
from app.services.auth_service import AuthService, InvalidCredentialsError
from app.security.authentication import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register_user(
    request: RegisterRequest,
    session: Session = Depends(get_database_session),
):
    service = UserService(session)

    try:
        user = service.register_user(
            request.username,
            str(request.email),
            request.password,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))

    return UserResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse)
def login_user(
    request: LoginRequest,
    session: Session = Depends(get_database_session),
):
    # Keep the submitted credential out of logs while making it clear what the
    # frontend sent and whether the password field arrived populated.
    print(
        "Login request received: "
        f"identifier={request.identifier!r}, "
        f"password=<redacted>, password_length={len(request.password)}"
    )
    service = AuthService(session)

    try:
        user = service.login(
            request.identifier,
            request.password,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=401,
            detail="Invalid username/email or password",
        )

    return LoginResponse(
        access_token=service.create_access_token(user.id),
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_user_profile(
    user: User = Depends(get_current_user),
):
    return UserResponse.model_validate(user)
