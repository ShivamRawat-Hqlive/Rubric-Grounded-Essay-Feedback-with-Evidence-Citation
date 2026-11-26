"""Environment-backed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class ConfigurationError(ValueError):
    """Raised when a required runtime setting is missing or unsafe."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
    )

    database_url: str | None = None
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, gt=0, le=65535)
    postgres_user: str = "essay"
    postgres_password: SecretStr | None = None
    postgres_database: str = Field(
        default="essay_eval",
        validation_alias="POSTGRES_DB",
    )
    jwt_secret_key: SecretStr | None = None
    jwt_refresh_secret_key: SecretStr | None = None
    jwt_access_token_expire_minutes: int = Field(default=15, gt=0, le=1440)
    refresh_token_expire_days: int = Field(default=7, gt=0, le=90)
    refresh_cookie_secure: bool = False
    file_storage_dir: Path = Path("./data/files")
    max_upload_mb: int = Field(default=10, gt=0, le=50)
    max_extracted_chars: int = Field(default=500_000, gt=0, le=2_000_000)
    llm_provider: str | None = None
    openai_api_key: SecretStr | None = None
    openai_chat_model: str = Field(default="gpt-4o-mini", min_length=1, max_length=100)
    llm_request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    max_evaluation_chars: int = Field(default=30_000, gt=0, le=500_000)
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    ocr_enabled: bool = False
    ocr_provider: str = Field(default="trocr", min_length=1, max_length=32)
    ocr_model_id: str = Field(
        default="microsoft/trocr-base-handwritten",
        min_length=1,
        max_length=200,
    )
    ocr_device: str = Field(default="cpu", min_length=1, max_length=16)

    @field_validator("llm_provider")
    @classmethod
    def normalize_llm_provider(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def resolved_file_storage_dir(self) -> Path:
        storage_dir = self.file_storage_dir.expanduser()
        if not storage_dir.is_absolute():
            storage_dir = REPOSITORY_ROOT / storage_dir
        return storage_dir.resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def require_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        password = (
            self.postgres_password.get_secret_value()
            if self.postgres_password
            else ""
        )
        if not password:
            raise ConfigurationError(
                "POSTGRES_PASSWORD is not configured; set the PostgreSQL "
                "connection settings in the repository-root .env file."
            )
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_database,
        ).render_as_string(hide_password=False)

    def require_jwt_secret(self) -> str:
        secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
        if len(secret.encode("utf-8")) < 32 or secret.startswith("change-me"):
            raise ConfigurationError(
                "JWT_SECRET_KEY must contain at least 32 random bytes."
            )
        return secret


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
