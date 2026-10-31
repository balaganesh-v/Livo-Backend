
from sqlalchemy.exc import IntegrityError

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.security.password_security import hash_password


class UserService:
    def __init__(self, session):
        self.session = session
        self.repository = UserRepository(session)

    def register_user(self, username, email, password):
        username = username.strip().lower()
        email = email.strip().lower()

        existing_user = self.repository.get_user_by_username(username)

        if existing_user is not None:
            raise ValueError("Username is already registered")

        existing_email = self.repository.get_user_by_email(email)

        if existing_email is not None:
            raise ValueError("Email is already registered")

        user = User(
            name=username,
            username=username,
            email=email,
            password_hash=hash_password(password),
            is_active=True,
        )

        self.repository.add_user(user)

        try:
            self.session.commit()
            self.session.refresh(user)
        except IntegrityError:
            self.session.rollback()
            raise ValueError("Username or email is already registered")

        return user
    
