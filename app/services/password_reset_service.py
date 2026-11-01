import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.database.config import settings
from app.models.password_reset_token import PasswordResetToken
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.security.password_security import hash_password
from app.services.email_service import EmailService


OTP_TTL = timedelta(minutes=10)
RESET_TOKEN_TTL = timedelta(minutes=15)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_OTP_ATTEMPTS = 5
GENERIC_MESSAGE = (
    "If an account exists for that email, a verification code has been sent."
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _reset_secret() -> bytes:
    if not settings.reset_token_secret:
        raise RuntimeError("RESET_TOKEN_SECRET is not configured")
    return settings.reset_token_secret.encode("utf-8")


def _hash_otp(otp: str) -> str:
    return hmac.new(_reset_secret(), otp.encode("ascii"), hashlib.sha256).hexdigest()


def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PasswordResetService:
    def __init__(self, session):
        self.session = session
        self.users = UserRepository(session)
        self.tokens = PasswordResetRepository(session)
        self.email = EmailService()

    def request_otp(self, email: str) -> None:
        self._issue_otp(email)

    def resend_otp(self, email: str) -> None:
        self._issue_otp(email)

    def _issue_otp(self, email: str) -> None:
        normalized_email = str(email).strip().lower()
        user = self.users.get_user_by_email(normalized_email)
        if user is None or not user.is_active:
            return

        now = _now()
        latest = self.tokens.get_latest_for_user(user.id)
        if latest is not None and now - latest.created_at < RESEND_COOLDOWN:
            return

        try:
            secret = _reset_secret()
            otp = f"{secrets.randbelow(1_000_000):06d}"
            for previous in self.tokens.get_unused_for_user(user.id):
                previous.used_at = now

            token = PasswordResetToken(
                user_id=user.id,
                otp_hash=hmac.new(secret, otp.encode("ascii"), hashlib.sha256).hexdigest(),
                expires_at=now + OTP_TTL,
                attempts=0,
            )
            self.tokens.add(token)
            self.session.flush()
            self.email.send_password_reset_otp(normalized_email, otp)
            self.session.commit()
        except Exception:
            self.session.rollback()
            # Keep the same response for unknown addresses and delivery/config errors.

    def verify_otp(self, email: str, otp: str) -> str | None:
        user = self.users.get_user_by_email(str(email).strip().lower())
        if user is None or not user.is_active:
            return None

        now = _now()
        token = self.tokens.get_latest_unused_for_user(user.id)
        if (
            token is None
            or token.verified_at is not None
            or token.expires_at <= now
            or token.attempts >= MAX_OTP_ATTEMPTS
        ):
            return None

        try:
            expected_hash = _hash_otp(otp)
        except RuntimeError:
            return None

        if not hmac.compare_digest(token.otp_hash, expected_hash):
            token.attempts += 1
            if token.attempts >= MAX_OTP_ATTEMPTS:
                token.used_at = now
            self.session.commit()
            return None

        reset_token = secrets.token_urlsafe(32)
        token.verified_at = now
        token.reset_token_hash = _hash_reset_token(reset_token)
        token.expires_at = now + RESET_TOKEN_TTL
        self.session.commit()
        return reset_token

    def reset_password(self, reset_token: str, new_password: str) -> bool:
        token_record = self.tokens.get_by_reset_token_hash(
            _hash_reset_token(reset_token)
        )
        now = _now()
        if (
            token_record is None
            or token_record.verified_at is None
            or token_record.expires_at <= now
        ):
            return False

        user = self.users.get_user_by_id(token_record.user_id)
        if user is None or not user.is_active:
            return False

        try:
            user.password_hash = hash_password(new_password)
            for outstanding in self.tokens.get_unused_for_user(user.id):
                outstanding.used_at = now
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return True
