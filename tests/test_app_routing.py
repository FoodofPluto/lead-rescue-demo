import inspect

from config import Settings
from app import (
    inquiries_to_csv,
    inquiry_export_rows,
    is_honeypot_filled,
    logout_operator_session,
    looks_like_email,
    operator_unlocked,
    public_contact_link,
    public_follow_up_link,
    public_route_name,
    render_cta_demo_request_form,
    render_customer_lead_form,
    render_public_landing,
)


def settings():
    return Settings(
        app_base_url="https://lead-rescue.example",
        app_base_url_configured=True,
        admin_password="secret",
        owner_email="owner@example.com",
        email_provider="disabled",
        from_email="Lead Rescue <noreply@example.com>",
        resend_api_key="",
        smtp_host="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        database_path=":memory:",
    )


def test_form_lead_route_uses_customer_form_not_homepage():
    assert public_route_name("lead", None) == "customer_lead_form"
    assert public_route_name("abc-plumbing", None) == "customer_lead_form"
    assert public_route_name(None, None, "1") == "contact_form"
    assert public_route_name(None, None) == "homepage"
    assert public_route_name("lead", "1") == "operator"


def test_app_import_exposes_email_validator():
    assert looks_like_email("owner@example.com") is True
    assert looks_like_email("not-an-email") is False


def test_public_homepage_copy_does_not_expose_admin_route():
    source = inspect.getsource(render_public_landing)

    assert "?admin=1" not in source
    assert "ADMIN_PASSWORD" not in source
    assert "Operator route" not in source
    assert "setup area with" not in source


def test_public_homepage_cta_routes_to_contact_form():
    assert public_contact_link(settings()) == "https://lead-rescue.example/?contact=1"
    assert public_follow_up_link(settings()) == "https://lead-rescue.example/?form=lead"
    assert public_follow_up_link(settings(), "ABC Plumbing") == "https://lead-rescue.example/?form=abc-plumbing"


def test_contact_route_renders_lead_rescue_demo_request_form():
    source = inspect.getsource(render_cta_demo_request_form)

    assert "Request a Lead Rescue Demo" in source
    assert "Request Demo" in source
    assert "cta_demo_request" in source


def test_form_lead_route_renders_customer_facing_intake_form():
    source = inspect.getsource(render_customer_lead_form)

    assert "customer_lead_form" in source
    assert "customer_lead" in source
    assert "notify_for_customer_lead_request" in source
    assert "get_customer_form_by_slug" in source
    assert "get_default_customer_form_config" in source
    assert "Customer form not found" in source


def test_honeypot_detection_is_blank_safe():
    assert is_honeypot_filled("") is False
    assert is_honeypot_filled("   ") is False
    assert is_honeypot_filled("https://spam.example") is True


def test_recent_inquiry_export_csv_is_null_safe():
    rows = [
        {
            "created_at": "2026-06-22T18:00:00+00:00",
            "name": "Taylor",
            "email": "taylor@example.com",
            "phone": "555",
            "message": "Need help",
            "customer_form_client_name": "",
            "customer_form_slug": "",
            "destination_email_used": "",
        }
    ]

    export_rows = inquiry_export_rows(rows)
    csv_text = inquiries_to_csv(rows)

    assert export_rows[0]["client_form_name"] == "Legacy/default"
    assert export_rows[0]["form_slug"] == "Unknown"
    assert "submitted,name,email,phone,message,client_form_name,form_slug,destination_email_used" in csv_text
    assert "Taylor" in csv_text


def test_logout_operator_session_clears_auth(monkeypatch):
    state = {"admin_authenticated": True}
    monkeypatch.setattr("app.st.session_state", state)

    logout_operator_session()

    assert "admin_authenticated" not in state


def test_operator_unlocked_requires_configured_admin_password(monkeypatch):
    calls = []

    class FakeStreamlit:
        session_state = {}

        @staticmethod
        def error(message):
            calls.append(("error", message))

        @staticmethod
        def write(message):
            calls.append(("write", message))

        @staticmethod
        def code(value, language=None):
            calls.append(("code", value, language))

    locked_settings = Settings(
        app_base_url="https://lead-rescue.example",
        app_base_url_configured=True,
        admin_password="",
        owner_email="owner@example.com",
        email_provider="disabled",
        from_email="Lead Rescue <noreply@example.com>",
        resend_api_key="",
        smtp_host="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        database_path=":memory:",
    )
    monkeypatch.setattr("app.st", FakeStreamlit)

    assert operator_unlocked(locked_settings) is False
    assert ("error", "Operator area is locked.") in calls
