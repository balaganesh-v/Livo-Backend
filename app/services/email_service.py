import smtplib
import ssl
from email.message import EmailMessage

from app.database.config import settings


class EmailConfigurationError(RuntimeError):
    """Raised when SMTP settings needed for email delivery are missing."""


class EmailService:
    def send_password_reset_otp(self, recipient: str, otp: str) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise EmailConfigurationError("SMTP host and sender email are required")

        message = EmailMessage()
        message["Subject"] = "Your Livo password reset code"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient
        message.set_content(
            f"Your Livo password reset code is {otp}. "
            "It expires in 10 minutes. If you did not request this code, "
            "you can ignore this email."
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
