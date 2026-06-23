import os

from config import get_settings


ENV_KEYS = [
    "APP_BASE_URL",
    "ADMIN_PASSWORD",
    "OWNER_EMAIL",
    "DEFAULT_DESTINATION_EMAIL",
    "EMAIL_PROVIDER",
    "FROM_EMAIL",
    "RESEND_API_KEY",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "DATABASE_PATH",
]


def clear_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_get_settings_uses_safe_defaults_when_optional_email_is_missing(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    settings = get_settings()

    assert settings.app_base_url == "http://localhost:8501"
    assert settings.app_base_url_configured is False
    assert settings.admin_password == ""
    assert settings.owner_email == ""
    assert settings.email_provider == "disabled"
    assert settings.database_path == "leads.db"


def test_get_settings_loads_dotenv_without_overriding_environment(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADMIN_PASSWORD", "from-real-env")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "APP_BASE_URL=https://lead-rescue.example",
                "ADMIN_PASSWORD=from-dotenv",
                "DEFAULT_DESTINATION_EMAIL=default@example.com",
                "EMAIL_PROVIDER=resend",
                "RESEND_API_KEY=test-key",
                "DATABASE_PATH=hosted.db",
            ]
        ),
        encoding="utf-8",
    )

    settings = get_settings()

    assert settings.app_base_url == "https://lead-rescue.example"
    assert settings.app_base_url_configured is True
    assert settings.admin_password == "from-real-env"
    assert settings.owner_email == "default@example.com"
    assert settings.email_provider == "resend"
    assert settings.resend_api_key == "test-key"
    assert settings.database_path == "hosted.db"
    assert os.environ["ADMIN_PASSWORD"] == "from-real-env"
