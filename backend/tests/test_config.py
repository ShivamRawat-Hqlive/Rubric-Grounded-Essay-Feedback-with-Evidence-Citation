"""Database URL construction tests."""

from pydantic import SecretStr
from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_postgres_url_uses_compose_connection_settings() -> None:
    settings = Settings(
        postgres_host="127.0.0.1",
        postgres_port=55432,
        postgres_user="essay_app",
        postgres_password=SecretStr("p@ss:word/with?reserved#chars"),
        postgres_database="essay_test",
    )

    url = make_url(settings.require_database_url())
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "127.0.0.1"
    assert url.port == 55432
    assert url.username == "essay_app"
    assert url.password == "p@ss:word/with?reserved#chars"
    assert url.database == "essay_test"


def test_postgres_settings_use_environment_variable_names(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "essay_app")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-only-password-value")
    monkeypatch.setenv("POSTGRES_DB", "essay_test")

    settings = Settings(_env_file=None)
    url = make_url(settings.require_database_url())
    assert (url.host, url.port, url.username, url.database) == (
        "127.0.0.1",
        5433,
        "essay_app",
        "essay_test",
    )


def test_document_limits_and_storage_load_from_environment(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("FILE_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MAX_UPLOAD_MB", "2")
    monkeypatch.setenv("MAX_EXTRACTED_CHARS", "1200")

    settings = Settings(_env_file=None)

    assert settings.resolved_file_storage_dir == tmp_path.resolve()
    assert settings.max_upload_bytes == 2 * 1024 * 1024
    assert settings.max_extracted_chars == 1200
