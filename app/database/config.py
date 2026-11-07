from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Database configuration
    app_env: str = Field(default="production", validation_alias="APP_ENV")
    db_host: str = Field(default="localhost", validation_alias="DB_HOST")
    db_port: int = Field(default=3306, validation_alias="DB_PORT")
    db_name: str = Field(
        default="ai_folder_organizer",
        validation_alias="DB_NAME",
    )
    db_user: str = Field(default="root", validation_alias="DB_USER")
    db_password: str = Field(default="", validation_alias="DB_PASSWORD")
    file_content_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        gt=0,
        validation_alias="FILE_CONTENT_MAX_BYTES",
    )
    file_content_max_chars: int = Field(
        default=100_000,
        gt=0,
        validation_alias="FILE_CONTENT_MAX_CHARS",
    )
    jwt_secret: str = Field(default="", validation_alias="JWT_SECRET")
    access_token_minutes: int = Field(
        default=15, gt=0, validation_alias="ACCESS_TOKEN_MINUTES"
    )
    refresh_token_days: int = Field(
        default=14, gt=0, validation_alias="REFRESH_TOKEN_DAYS"
    )
    frontend_origin: str = Field(
        default="http://localhost:5173", validation_alias="FRONTEND_ORIGIN"
    )
    refresh_cookie_secure: bool = Field(
        default=False, validation_alias="REFRESH_COOKIE_SECURE"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="gemma3:4b", validation_alias="OLLAMA_MODEL")
    ollama_timeout_seconds: float = Field(
        default=60.0, gt=0, validation_alias="OLLAMA_TIMEOUT_SECONDS"
    )

    model_config = SettingsConfigDict(
        # Resolve the backend's own .env regardless of the process working
        # directory (for example, when launched from the frontend directory).
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> URL:
        """Build the database URL without exposing or misparsing credentials."""
        return URL.create(
            drivername="mysql+pymysql",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


settings = Settings()

__all__ = ["Settings", "settings"]
