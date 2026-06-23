from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    app_base_url: str
    app_base_url_configured: bool
    admin_password: str
    owner_email: str
    email_provider: str
    from_email: str
    resend_api_key: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    database_path: str


def env_value(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is not None:
        return value
    try:
        import streamlit as st

        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


def get_settings() -> Settings:
    load_dotenv()
    app_base_url = env_value("APP_BASE_URL", "http://localhost:8501")
    default_destination_email = env_value("DEFAULT_DESTINATION_EMAIL", "")
    return Settings(
        app_base_url=app_base_url,
        app_base_url_configured=bool(env_value("APP_BASE_URL", "")),
        admin_password=env_value("ADMIN_PASSWORD", ""),
        owner_email=env_value("OWNER_EMAIL", default_destination_email),
        email_provider=env_value("EMAIL_PROVIDER", "disabled").lower(),
        from_email=env_value("FROM_EMAIL", "Lead Rescue AI <noreply@example.com>"),
        resend_api_key=env_value("RESEND_API_KEY", ""),
        smtp_host=env_value("SMTP_HOST", ""),
        smtp_port=int(env_value("SMTP_PORT", "587")),
        smtp_username=env_value("SMTP_USERNAME", ""),
        smtp_password=env_value("SMTP_PASSWORD", ""),
        database_path=env_value("DATABASE_PATH", "leads.db"),
    )
