from sqlalchemy import select

from app.models.password_reset_token import PasswordResetToken


class PasswordResetRepository:
    def __init__(self, session):
        self.session = session

    def get_latest_for_user(self, user_id: int) -> PasswordResetToken | None:
        statement = (
            select(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id)
            .order_by(PasswordResetToken.created_at.desc(), PasswordResetToken.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def get_latest_unused_for_user(self, user_id: int) -> PasswordResetToken | None:
        statement = (
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
            )
            .order_by(PasswordResetToken.created_at.desc(), PasswordResetToken.id.desc())
            .limit(1)
            .with_for_update()
        )
        return self.session.scalar(statement)

    def get_by_reset_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        statement = select(PasswordResetToken).where(
            PasswordResetToken.reset_token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
        ).with_for_update()
        return self.session.scalar(statement)

    def get_unused_for_user(self, user_id: int) -> list[PasswordResetToken]:
        statement = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
        return list(self.session.scalars(statement))

    def add(self, token: PasswordResetToken) -> PasswordResetToken:
        self.session.add(token)
        return token
