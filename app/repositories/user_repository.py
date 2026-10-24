
from sqlalchemy import select, func

from app.models.user import User


class UserRepository:
    def __init__(self, session):
        self.session = session

    def get_user_by_id(self, user_id):
        return self.session.get(User, user_id)

    def get_user_by_email(self, email):
        statement = select(User).where(
            func.lower(User.email) == email.lower()
        )
        return self.session.scalar(statement)

    def get_user_by_username(self, username):
        statement = select(User).where(
            func.lower(User.username) == username.lower()
        )
        return self.session.scalar(statement)

    def get_user_by_email_or_username(self, identifier):
        statement = select(User).where(
            (func.lower(User.email) == identifier.lower())
            | (func.lower(User.username) == identifier.lower())
        )
        return self.session.scalar(statement)

    def add_user(self, user):
        self.session.add(user)
        return user
