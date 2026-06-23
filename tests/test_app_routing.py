import inspect

from config import Settings
from app import (
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
    assert public_route_name(None, None, "1") == "contact_form"
    assert public_route_name(None, None) == "homepage"
    assert public_route_name("lead", "1") == "operator"


def test_public_homepage_copy_does_not_expose_admin_route():
    source = inspect.getsource(render_public_landing)

    assert "?admin=1" not in source
    assert "ADMIN_PASSWORD" not in source
    assert "Operator route" not in source
    assert "setup area with" not in source


def test_public_homepage_cta_routes_to_contact_form():
    assert public_contact_link(settings()) == "https://lead-rescue.example/?contact=1"
    assert public_follow_up_link(settings()) == "https://lead-rescue.example/?form=lead"


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
